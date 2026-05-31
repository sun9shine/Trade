"""
Tests for the Arbitrage Router — latency arb, negative risk arb, kill switch.
"""

import math
import pytest
from unittest.mock import AsyncMock, MagicMock, patch

from app.engine.arbitrage_router import ArbitrageRouter, ArbSignal, ExecutionResult
from app.connectors.forex_engine import TickData


class TestArbitrageRouter:
    """Tests for ArbitrageRouter class."""

    def setup_method(self):
        """Set up test fixtures."""
        self.polymarket = MagicMock()
        self.premu = MagicMock()
        self.monaco = MagicMock()

        self.router = ArbitrageRouter(
            polymarket=self.polymarket,
            premu=self.premu,
            monaco=self.monaco,
        )

    # ─── FAIR PROBABILITY CALCULATION ─────────────────────────────────────────

    def test_calculate_fair_probability_small_move(self):
        """Small moves should map to lower probabilities."""
        prob = ArbitrageRouter._calculate_fair_probability(0.5, "up")
        assert 0.30 <= prob <= 0.50

    def test_calculate_fair_probability_large_move(self):
        """Large moves should map to higher probabilities."""
        prob = ArbitrageRouter._calculate_fair_probability(4.0, "up")
        assert 0.85 <= prob <= 0.95

    def test_calculate_fair_probability_medium_move(self):
        """2% move should be around 50% (midpoint of logistic)."""
        prob = ArbitrageRouter._calculate_fair_probability(2.0, "up")
        # At x0=2.0, logistic gives 0.5
        assert 0.45 <= prob <= 0.55

    def test_calculate_fair_probability_clamped_low(self):
        """Very small moves should be clamped at 0.30."""
        prob = ArbitrageRouter._calculate_fair_probability(0.01, "up")
        assert prob >= 0.30

    def test_calculate_fair_probability_clamped_high(self):
        """Very large moves should be clamped at 0.95."""
        prob = ArbitrageRouter._calculate_fair_probability(10.0, "up")
        assert prob <= 0.95

    # ─── LATENCY ARBITRAGE ────────────────────────────────────────────────────

    @pytest.mark.asyncio
    async def test_latency_arb_detects_opportunity(self):
        """Should detect arbitrage when gap exceeds threshold."""
        tick = TickData(
            symbol="EURUSD",
            bid=1.0850,
            ask=1.0852,
            spread=0.0002,
            source="oanda",
            timestamp_ms=1717200000000,
        )

        target_markets = {
            "EURUSD": {
                "platform": "polymarket",
                "market_id": "0xtest123",
            }
        }

        # Mock the market odds fetch — market shows 0.40 probability
        # while fair value from a big move would be much higher
        self.router._fetch_market_odds = AsyncMock(return_value={"up": 0.40, "down": 0.60})

        signals = await self.router.check_latency_arb(
            tick=tick,
            pct_change=3.0,  # Big move
            target_markets=target_markets,
        )

        # Should detect opportunity because fair_prob(3%) ≈ 0.73 vs market 0.40 = 33% gap
        assert len(signals) >= 1
        assert signals[0].signal_type == "latency_arb"
        assert signals[0].platform == "polymarket"

    @pytest.mark.asyncio
    async def test_latency_arb_no_opportunity_small_gap(self):
        """Should NOT trigger when gap is below threshold."""
        tick = TickData(
            symbol="EURUSD",
            bid=1.0850,
            ask=1.0852,
            spread=0.0002,
            source="oanda",
            timestamp_ms=1717200000000,
        )

        target_markets = {
            "EURUSD": {
                "platform": "premu",
                "market_id": "abc123",
            }
        }

        # Market odds close to fair value — no opportunity
        self.router._fetch_market_odds = AsyncMock(return_value={"up": 0.50, "down": 0.50})

        signals = await self.router.check_latency_arb(
            tick=tick,
            pct_change=2.0,  # 2% move → ~50% fair prob = no gap
            target_markets=target_markets,
        )

        assert len(signals) == 0

    @pytest.mark.asyncio
    async def test_latency_arb_kill_switch_blocks(self):
        """Kill switch should prevent any signals."""
        self.router._kill_switch = True

        tick = TickData(
            symbol="EURUSD", bid=1.0, ask=1.0, spread=0.0,
            source="oanda", timestamp_ms=0,
        )

        signals = await self.router.check_latency_arb(
            tick=tick, pct_change=5.0, target_markets={"EURUSD": {"platform": "polymarket", "market_id": "x"}}
        )
        assert signals == []

    # ─── NEGATIVE RISK ARBITRAGE ──────────────────────────────────────────────

    @pytest.mark.asyncio
    async def test_negative_risk_arb_detects_opportunity(self):
        """Should detect when total implied prob < 96%."""
        # Mock outcomes with total ask = 0.90 (below 0.96 threshold)
        self.router._fetch_all_outcomes = AsyncMock(return_value=[
            {"ask_price": 0.45},
            {"ask_price": 0.45},
        ])

        signal = await self.router.check_negative_risk_arb(
            market_ids={"polymarket": "0xtest"}
        )

        assert signal is not None
        assert signal.signal_type == "neg_risk_arb"
        assert signal.direction == "buy_all"
        assert signal.expected_edge_pct == pytest.approx(10.0, abs=0.1)

    @pytest.mark.asyncio
    async def test_negative_risk_arb_no_opportunity(self):
        """Should NOT trigger when total > threshold."""
        # Mock outcomes with total ask = 1.02 (above threshold)
        self.router._fetch_all_outcomes = AsyncMock(return_value=[
            {"ask_price": 0.51},
            {"ask_price": 0.51},
        ])

        signal = await self.router.check_negative_risk_arb(
            market_ids={"polymarket": "0xtest"}
        )

        assert signal is None

    # ─── KILL SWITCH ──────────────────────────────────────────────────────────

    @pytest.mark.asyncio
    async def test_kill_switch_cancels_all(self):
        """Kill switch should cancel orders on all platforms."""
        self.polymarket.cancel_all_orders = AsyncMock(return_value=True)
        self.premu.cancel_all_positions = AsyncMock(return_value=True)
        self.monaco.cancel_all_orders = AsyncMock(return_value=True)

        await self.router.activate_kill_switch()

        assert self.router._kill_switch is True
        self.polymarket.cancel_all_orders.assert_called_once()
        self.premu.cancel_all_positions.assert_called_once()
        self.monaco.cancel_all_orders.assert_called_once()

    def test_deactivate_kill_switch(self):
        """Should re-enable trading."""
        self.router._kill_switch = True
        self.router.deactivate_kill_switch()
        assert self.router._kill_switch is False

    @pytest.mark.asyncio
    async def test_execute_blocked_by_kill_switch(self):
        """Execution should fail when kill switch is active."""
        self.router._kill_switch = True

        signal = ArbSignal(
            signal_type="latency_arb",
            source_symbol="EURUSD",
            platform="polymarket",
            market_id="test",
            expected_edge_pct=5.0,
            direction="up",
            timestamp_ms=0,
        )

        result = await self.router.execute_signal(signal)
        assert result.success is False
        assert "Kill switch" in result.error
