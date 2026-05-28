"""
Arbitrage Router — Core execution logic for:
1. Latency Arbitrage (Forex spike → prediction market delay)
2. Negative Risk Arbitrage (multi-outcome mispricing across DEXs)
"""

import asyncio
import time
from dataclasses import dataclass
from typing import Optional

import structlog

from app.config import risk_settings
from app.connectors.forex_engine import TickData
from app.connectors.polymarket import PolymarketConnector, PolymarketOrder
from app.connectors.premu import PremuConnector
from app.connectors.monaco import MonacoConnector, MonacoMarketOrder

logger = structlog.get_logger(__name__)


@dataclass
class ArbSignal:
    """Represents a detected arbitrage opportunity."""
    signal_type: str  # "latency_arb" or "neg_risk_arb"
    source_symbol: str
    platform: str
    market_id: str
    expected_edge_pct: float
    direction: str  # "up", "down", or "buy_all"
    timestamp_ms: int


@dataclass
class ExecutionResult:
    """Result of an arbitrage execution attempt."""
    success: bool
    signal: ArbSignal
    tx_hash: Optional[str] = None
    amount_usd: float = 0.0
    error: Optional[str] = None


class ArbitrageRouter:
    """
    Main arbitrage routing engine. Receives forex anomaly signals and macro events,
    checks prediction market prices for arbitrage opportunities, and executes trades.
    """

    def __init__(
        self,
        polymarket: PolymarketConnector,
        premu: PremuConnector,
        monaco: MonacoConnector,
    ):
        self.polymarket = polymarket
        self.premu = premu
        self.monaco = monaco
        self._kill_switch = risk_settings.kill_switch_enabled
        self._active_signals: list[ArbSignal] = []

    # ─── LATENCY ARBITRAGE ────────────────────────────────────────────────────

    async def check_latency_arb(
        self,
        tick: TickData,
        pct_change: float,
        target_markets: dict[str, dict],
    ) -> list[ArbSignal]:
        """
        When forex spike detected, check if prediction markets have a lagging adjustment.
        Execute if mispricing gap > threshold (default 1.5%).

        Args:
            tick: The forex tick that triggered the anomaly
            pct_change: Magnitude of the price move (%)
            target_markets: Mapping of symbol → {platform, market_id, outcome_up, outcome_down}
        """
        if self._kill_switch:
            logger.warning("arb_router.kill_switch_active")
            return []

        signals = []
        min_gap = risk_settings.latency_arb_min_gap_pct

        for symbol, market_info in target_markets.items():
            if tick.symbol != symbol:
                continue

            platform = market_info["platform"]
            market_id = market_info["market_id"]

            # Get current prediction market odds
            current_odds = await self._fetch_market_odds(platform, market_id)
            if current_odds is None:
                continue

            # Calculate implied fair value from forex move
            direction = "up" if pct_change > 0 else "down"
            fair_probability = self._calculate_fair_probability(pct_change, direction)

            # Compare with market's current implied probability
            market_prob = current_odds.get(direction, 0.5)
            gap_pct = abs(fair_probability - market_prob) * 100

            if gap_pct >= min_gap:
                signal = ArbSignal(
                    signal_type="latency_arb",
                    source_symbol=tick.symbol,
                    platform=platform,
                    market_id=market_id,
                    expected_edge_pct=gap_pct,
                    direction=direction,
                    timestamp_ms=int(time.time() * 1000),
                )
                signals.append(signal)
                logger.info(
                    "arb.latency_opportunity",
                    symbol=tick.symbol,
                    platform=platform,
                    gap_pct=round(gap_pct, 3),
                    direction=direction,
                )

        return signals

    # ─── NEGATIVE RISK ARBITRAGE ──────────────────────────────────────────────

    async def check_negative_risk_arb(
        self,
        market_ids: dict[str, str],  # {platform: market_id}
    ) -> Optional[ArbSignal]:
        """
        Monitor multi-outcome event pools. If total implied probability of all
        outcomes falls below 96% (0.96), execute buy-all-outcomes for risk-free profit.

        This exploits inefficiency where the sum of prices for all outcomes < 1.0.
        """
        if self._kill_switch:
            return None

        threshold = risk_settings.neg_risk_threshold

        for platform, market_id in market_ids.items():
            outcomes = await self._fetch_all_outcomes(platform, market_id)
            if not outcomes:
                continue

            total_implied = sum(o["ask_price"] for o in outcomes)

            if total_implied < threshold:
                edge_pct = (1.0 - total_implied) * 100
                signal = ArbSignal(
                    signal_type="neg_risk_arb",
                    source_symbol="multi-outcome",
                    platform=platform,
                    market_id=market_id,
                    expected_edge_pct=edge_pct,
                    direction="buy_all",
                    timestamp_ms=int(time.time() * 1000),
                )
                logger.info(
                    "arb.negative_risk_opportunity",
                    platform=platform,
                    total_implied=round(total_implied, 4),
                    edge_pct=round(edge_pct, 3),
                )
                return signal

        return None

    # ─── EXECUTION ────────────────────────────────────────────────────────────

    async def execute_signal(self, signal: ArbSignal) -> ExecutionResult:
        """Route and execute an arbitrage signal on the target platform."""
        if self._kill_switch:
            return ExecutionResult(success=False, signal=signal, error="Kill switch active")

        max_size = risk_settings.max_position_size_usd

        try:
            if signal.platform == "polymarket":
                return await self._execute_polymarket(signal, max_size)
            elif signal.platform == "premu":
                return await self._execute_premu(signal, max_size)
            elif signal.platform == "monaco":
                return await self._execute_monaco(signal, max_size)
            else:
                return ExecutionResult(
                    success=False, signal=signal, error=f"Unknown platform: {signal.platform}"
                )
        except Exception as e:
            logger.error("arb.execution_error", error=str(e), signal=signal)
            return ExecutionResult(success=False, signal=signal, error=str(e))

    async def _execute_polymarket(self, signal: ArbSignal, max_size: float) -> ExecutionResult:
        """Execute on Polymarket CLOB."""
        # For latency arb: buy the underpriced outcome
        # For neg risk arb: buy all outcomes
        order = PolymarketOrder(
            token_id=signal.market_id,
            side="BUY",
            price=0.50,  # Will be refined based on order book
            size=max_size / 0.50,  # Shares at the target price
        )
        order_id = await self.polymarket.place_order(order)
        return ExecutionResult(
            success=order_id is not None,
            signal=signal,
            tx_hash=order_id,
            amount_usd=max_size,
        )

    async def _execute_premu(self, signal: ArbSignal, max_size: float) -> ExecutionResult:
        """Execute on Premu Fast Markets."""
        from web3 import Web3

        outcome = 0 if signal.direction == "up" else 1
        amount_wei = Web3.to_wei(max_size, "mwei")  # USDC has 6 decimals

        tx_hash = await self.premu.buy_outcome_with_permit(
            market_id=bytes.fromhex(signal.market_id),
            outcome=outcome,
            amount_wei=amount_wei,
        )
        return ExecutionResult(
            success=tx_hash is not None,
            signal=signal,
            tx_hash=tx_hash,
            amount_usd=max_size,
        )

    async def _execute_monaco(self, signal: ArbSignal, max_size: float) -> ExecutionResult:
        """Execute on Monaco Protocol (Solana)."""
        order = MonacoMarketOrder(
            market_pk=signal.market_id,
            outcome_index=0 if signal.direction in ("up", "buy_all") else 1,
            side="for" if signal.direction in ("up", "buy_all") else "against",
            price=1.5,  # Will be refined based on order book
            stake=max_size,
        )
        tx_sig = await self.monaco.place_order(order)
        return ExecutionResult(
            success=tx_sig is not None,
            signal=signal,
            tx_hash=tx_sig,
            amount_usd=max_size,
        )

    # ─── KILL SWITCH ──────────────────────────────────────────────────────────

    async def activate_kill_switch(self):
        """Emergency: cancel ALL orders across ALL platforms simultaneously."""
        self._kill_switch = True
        logger.critical("arb_router.KILL_SWITCH_ACTIVATED")

        results = await asyncio.gather(
            self.polymarket.cancel_all_orders(),
            self.premu.cancel_all_positions(),
            self.monaco.cancel_all_orders(),
            return_exceptions=True,
        )

        for i, result in enumerate(results):
            platform = ["polymarket", "premu", "monaco"][i]
            if isinstance(result, Exception):
                logger.error("kill_switch.cancel_failed", platform=platform, error=str(result))
            else:
                logger.info("kill_switch.cancelled", platform=platform)

    def deactivate_kill_switch(self):
        """Re-enable trading after kill switch was triggered."""
        self._kill_switch = False
        logger.info("arb_router.kill_switch_deactivated")

    # ─── HELPERS ──────────────────────────────────────────────────────────────

    async def _fetch_market_odds(self, platform: str, market_id: str) -> Optional[dict]:
        """Fetch current odds from a specific platform."""
        try:
            if platform == "polymarket":
                outcomes = await self.polymarket.get_market_odds(market_id)
                if outcomes:
                    return {
                        "up": outcomes[0].implied_probability,
                        "down": outcomes[1].implied_probability if len(outcomes) > 1 else 0.5,
                    }
            elif platform == "premu":
                market = await self.premu.get_fast_market(bytes.fromhex(market_id))
                if market:
                    return {"up": market.up_odds, "down": market.down_odds}
            elif platform == "monaco":
                outcomes = await self.monaco.get_market_outcomes(market_id)
                if outcomes:
                    return {
                        "up": outcomes[0].implied_probability,
                        "down": outcomes[1].implied_probability if len(outcomes) > 1 else 0.5,
                    }
        except Exception as e:
            logger.error("arb.fetch_odds_failed", platform=platform, error=str(e))
        return None

    async def _fetch_all_outcomes(self, platform: str, market_id: str) -> list[dict]:
        """Fetch all outcome ask prices for negative risk calculation."""
        try:
            if platform == "polymarket":
                outcomes = await self.polymarket.get_market_odds(market_id)
                return [{"ask_price": o.best_ask} for o in outcomes]
            elif platform == "monaco":
                outcomes = await self.monaco.get_market_outcomes(market_id)
                return [{"ask_price": o.best_for_price} for o in outcomes]
        except Exception as e:
            logger.error("arb.fetch_outcomes_failed", platform=platform, error=str(e))
        return []

    @staticmethod
    def _calculate_fair_probability(pct_change: float, direction: str) -> float:
        """
        Map forex percentage change to a fair probability estimate.
        Uses a logistic curve to model market impact on prediction odds.
        """
        import math
        # Logistic curve: larger moves → higher probability of directional outcome
        # k controls steepness, x0 is midpoint
        k = 1.5
        x0 = 2.0  # 2% move maps to ~73% probability
        raw_prob = 1 / (1 + math.exp(-k * (abs(pct_change) - x0)))
        # Clamp between 0.30 and 0.95
        return max(0.30, min(0.95, raw_prob))
