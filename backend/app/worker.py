"""
Main Worker Loop — Orchestrates the entire arbitrage bot:
1. Forex streaming (MT5/OANDA) with anomaly detection
2. Periodic negative risk arbitrage scanning
3. Macro event processing pipeline
4. Real-time metrics broadcasting via Redis pub/sub

This is the entry point for the execution engine (runs separately from the API).
"""

import asyncio
import signal
import sys
import time
from typing import Optional

import structlog
import redis.asyncio as aioredis
import orjson

from app.config import app_settings, db_settings, risk_settings
from app.connectors.forex_engine import ForexEngine, TickData
from app.connectors.polymarket import PolymarketConnector
from app.connectors.premu import PremuConnector
from app.connectors.monaco import MonacoConnector
from app.engine.arbitrage_router import ArbitrageRouter, ArbSignal
from app.engine.webhook_handler import WebhookHandler
from app.market_mapping import market_mapping
from app.database import async_session_factory
from app.models import TradeExecution, OpenPosition, ForexTick, MetricsSnapshot

logger = structlog.get_logger(__name__)


class ArbitrageWorker:
    """
    Main orchestration worker. Runs continuously and coordinates:
    - Forex data streaming
    - Anomaly → arbitrage signal detection
    - Multi-platform execution
    - Periodic negative risk scanning
    - Metrics publishing
    """

    def __init__(self):
        # Connectors
        self.polymarket = PolymarketConnector()
        self.premu = PremuConnector()
        self.monaco = MonacoConnector()

        # Engine
        self.arb_router = ArbitrageRouter(
            polymarket=self.polymarket,
            premu=self.premu,
            monaco=self.monaco,
        )

        # Forex engine with callbacks
        self.forex_engine = ForexEngine(
            on_tick=self._on_tick,
            on_anomaly=self._on_forex_anomaly,
        )

        # Webhook handler
        self.webhook_handler = WebhookHandler(
            on_event_processed=self._on_macro_event,
        )

        # Redis for pub/sub metrics
        self._redis: Optional[aioredis.Redis] = None

        # State
        self._running = False
        self._tick_count = 0
        self._signal_count = 0
        self._execution_count = 0
        self._last_neg_risk_scan = 0
        self._neg_risk_interval = 30  # seconds

        # Metrics
        self._total_pnl = 0.0
        self._trades_today = 0

    async def start(self):
        """Initialize all connectors and start the main loop."""
        logger.info("worker.starting", env=app_settings.app_env)
        self._running = True

        # Connect to Redis
        try:
            self._redis = aioredis.from_url(db_settings.redis_url, decode_responses=True)
            await self._redis.ping()
            logger.info("worker.redis_connected")
        except Exception as e:
            logger.warning("worker.redis_unavailable", error=str(e))
            self._redis = None

        # Initialize blockchain connectors (graceful — don't crash if one fails)
        await self._init_connectors()

        # Register signal handlers for graceful shutdown
        loop = asyncio.get_running_loop()
        for sig in (signal.SIGINT, signal.SIGTERM):
            loop.add_signal_handler(sig, lambda: asyncio.create_task(self.shutdown()))

        # Start concurrent tasks
        tasks = [
            asyncio.create_task(self._forex_stream_task()),
            asyncio.create_task(self._negative_risk_scanner_task()),
            asyncio.create_task(self._metrics_publisher_task()),
            asyncio.create_task(self._health_check_task()),
        ]

        logger.info("worker.running", tasks=len(tasks))

        try:
            await asyncio.gather(*tasks, return_exceptions=True)
        except asyncio.CancelledError:
            logger.info("worker.cancelled")
        finally:
            await self.shutdown()

    async def shutdown(self):
        """Graceful shutdown — stop streams, close connections."""
        if not self._running:
            return
        self._running = False
        logger.info("worker.shutting_down")

        self.forex_engine.stop()

        if self._redis:
            await self._redis.close()

        logger.info(
            "worker.stopped",
            ticks_processed=self._tick_count,
            signals_generated=self._signal_count,
            trades_executed=self._execution_count,
        )

    async def _init_connectors(self):
        """Initialize blockchain connectors (non-fatal on failure)."""
        connectors = [
            ("polymarket", self.polymarket.initialize),
            ("premu", self.premu.initialize),
            ("monaco", self.monaco.initialize),
        ]
        for name, init_fn in connectors:
            try:
                await init_fn()
                logger.info("worker.connector_ready", connector=name)
            except Exception as e:
                logger.warning(
                    "worker.connector_init_failed",
                    connector=name,
                    error=str(e),
                    msg="Will retry on first use",
                )

    # ─── FOREX STREAMING TASK ─────────────────────────────────────────────────

    async def _forex_stream_task(self):
        """
        Main forex streaming loop with automatic failover:
        Try OANDA first (cross-platform), fall back to MT5 (Windows only).
        """
        while self._running:
            try:
                logger.info("worker.forex_stream_starting", source="oanda")
                await self.forex_engine.start_oanda_stream()
            except Exception as e:
                logger.error("worker.oanda_failed", error=str(e))

            if not self._running:
                break

            # Fallback to MT5
            try:
                logger.info("worker.forex_stream_starting", source="mt5")
                await self.forex_engine.start_mt5_stream()
            except Exception as e:
                logger.error("worker.mt5_failed", error=str(e))

            if not self._running:
                break

            # Both failed — retry after delay
            logger.warning("worker.forex_all_sources_failed", retry_in=10)
            await asyncio.sleep(10)

    # ─── NEGATIVE RISK SCANNER TASK ───────────────────────────────────────────

    async def _negative_risk_scanner_task(self):
        """
        Periodically scan all configured multi-outcome markets
        for negative risk arbitrage opportunities.
        """
        while self._running:
            try:
                now = time.time()
                if now - self._last_neg_risk_scan < self._neg_risk_interval:
                    await asyncio.sleep(5)
                    continue

                self._last_neg_risk_scan = now

                # Get configured negative risk pool market IDs
                market_ids = market_mapping.get_neg_risk_market_ids()
                if not market_ids:
                    await asyncio.sleep(self._neg_risk_interval)
                    continue

                signal = await self.arb_router.check_negative_risk_arb(market_ids)
                if signal:
                    self._signal_count += 1
                    await self._execute_and_record(signal)

            except Exception as e:
                logger.error("worker.neg_risk_scan_error", error=str(e))
                await asyncio.sleep(10)

    # ─── METRICS PUBLISHER TASK ───────────────────────────────────────────────

    async def _metrics_publisher_task(self):
        """Publish metrics to Redis every 5 seconds for WebSocket relay."""
        while self._running:
            try:
                metrics = {
                    "type": "metrics_update",
                    "data": {
                        "totalPnl": self._total_pnl,
                        "openPositions": 0,  # TODO: count from DB
                        "tradesToday": self._trades_today,
                        "avgLatency": 0.0,
                        "gasBalances": await self._get_gas_balances(),
                        "killSwitchActive": risk_settings.kill_switch_enabled,
                        "tickCount": self._tick_count,
                        "signalCount": self._signal_count,
                    },
                    "timestamp": int(time.time() * 1000),
                }

                if self._redis:
                    await self._redis.publish("metrics", orjson.dumps(metrics).decode())

                # Also save periodic snapshot to DB
                if self._tick_count % 1000 == 0 and self._tick_count > 0:
                    await self._save_metrics_snapshot(metrics["data"])

            except Exception as e:
                logger.error("worker.metrics_publish_error", error=str(e))

            await asyncio.sleep(5)

    # ─── HEALTH CHECK TASK ────────────────────────────────────────────────────

    async def _health_check_task(self):
        """Periodic health check logging."""
        while self._running:
            logger.info(
                "worker.heartbeat",
                ticks=self._tick_count,
                signals=self._signal_count,
                executions=self._execution_count,
                pnl=self._total_pnl,
                running=self._running,
            )
            await asyncio.sleep(60)

    # ─── CALLBACKS ────────────────────────────────────────────────────────────

    async def _on_tick(self, tick: TickData):
        """Called for every forex tick received."""
        self._tick_count += 1

        # Persist tick to DB every 100th tick (to avoid overload)
        if self._tick_count % 100 == 0:
            await self._save_tick(tick)

    async def _on_forex_anomaly(self, tick: TickData, pct_change: float):
        """
        Called when forex anomaly detected (>1.5% move).
        This is the primary trigger for latency arbitrage.
        """
        logger.info(
            "worker.anomaly_trigger",
            symbol=tick.symbol,
            pct_change=round(pct_change, 3),
        )

        # Get target markets for this symbol
        target_markets = market_mapping.get_target_markets_for_symbol(tick.symbol)
        if not target_markets:
            logger.debug("worker.no_target_markets", symbol=tick.symbol)
            return

        # Check for latency arbitrage opportunities
        signals = await self.arb_router.check_latency_arb(
            tick=tick,
            pct_change=pct_change,
            target_markets=target_markets,
        )

        for signal in signals:
            self._signal_count += 1
            await self._execute_and_record(signal)

    async def _on_macro_event(self, result: dict):
        """Called when a macro event is processed and deemed actionable."""
        event = result["event"]
        affected_pairs = result["affected_pairs"]

        logger.info(
            "worker.macro_event_action",
            event_type=event["event_type"],
            country=event["country"],
            affected_pairs=affected_pairs,
        )

        # For each affected pair, check target markets
        for symbol in affected_pairs:
            target_markets = market_mapping.get_target_markets_for_symbol(symbol)
            if not target_markets:
                continue

            # Create a synthetic tick for the arbitrage check
            # (The actual forex move will come from the stream)
            # This pre-positions us for the expected move
            event_markets = market_mapping.get_markets_for_event(
                event["event_type"], event["country"]
            )
            if event_markets:
                neg_risk = await self.arb_router.check_negative_risk_arb(event_markets)
                if neg_risk:
                    self._signal_count += 1
                    await self._execute_and_record(neg_risk)

    # ─── EXECUTION & PERSISTENCE ──────────────────────────────────────────────

    async def _execute_and_record(self, signal: ArbSignal):
        """Execute an arbitrage signal and record the result in the database."""
        result = await self.arb_router.execute_signal(signal)

        if result.success:
            self._execution_count += 1
            self._trades_today += 1
            logger.info(
                "worker.trade_executed",
                platform=signal.platform,
                direction=signal.direction,
                amount_usd=result.amount_usd,
                tx_hash=result.tx_hash,
            )
        else:
            logger.warning(
                "worker.trade_failed",
                platform=signal.platform,
                error=result.error,
            )

        # Persist to database
        await self._save_trade_execution(signal, result)

        # Publish to Redis for real-time dashboard update
        if self._redis:
            event_data = {
                "type": "trade_executed" if result.success else "trade_failed",
                "data": {
                    "platform": signal.platform,
                    "direction": signal.direction,
                    "amount_usd": result.amount_usd,
                    "tx_hash": result.tx_hash,
                    "signal_type": signal.signal_type,
                    "edge_pct": signal.expected_edge_pct,
                    "success": result.success,
                    "error": result.error,
                },
                "timestamp": int(time.time() * 1000),
            }
            await self._redis.publish("trades", orjson.dumps(event_data).decode())

    async def _save_trade_execution(self, signal: ArbSignal, result):
        """Persist trade execution to PostgreSQL."""
        try:
            async with async_session_factory() as session:
                trade = TradeExecution(
                    platform=signal.platform,
                    market_id=signal.market_id,
                    direction=signal.direction,
                    outcome=signal.direction,
                    quantity=result.amount_usd,
                    price=0.0,  # Filled from order book
                    total_cost_usd=result.amount_usd,
                    gas_cost_usd=None,
                    tx_hash=result.tx_hash,
                    status="confirmed" if result.success else "failed",
                    strategy=signal.signal_type,
                    signal_source=signal.source_symbol,
                )
                session.add(trade)
                await session.commit()
        except Exception as e:
            logger.error("worker.db_save_trade_failed", error=str(e))

    async def _save_tick(self, tick: TickData):
        """Persist forex tick to database (sampled)."""
        try:
            from datetime import datetime, timezone

            async with async_session_factory() as session:
                db_tick = ForexTick(
                    symbol=tick.symbol,
                    bid=tick.bid,
                    ask=tick.ask,
                    spread=tick.spread,
                    source=tick.source,
                    timestamp=datetime.fromtimestamp(tick.timestamp_ms / 1000, tz=timezone.utc),
                )
                session.add(db_tick)
                await session.commit()
        except Exception as e:
            logger.error("worker.db_save_tick_failed", error=str(e))

    async def _save_metrics_snapshot(self, metrics_data: dict):
        """Save periodic metrics snapshot to DB."""
        try:
            gas = metrics_data.get("gasBalances", {})
            async with async_session_factory() as session:
                snapshot = MetricsSnapshot(
                    total_pnl_usd=self._total_pnl,
                    open_position_count=metrics_data.get("openPositions", 0),
                    total_trades_today=self._trades_today,
                    polygon_gas_balance=gas.get("polygon", 0),
                    arbitrum_gas_balance=gas.get("arbitrum", 0),
                    solana_gas_balance=gas.get("solana", 0),
                    avg_latency_ms=metrics_data.get("avgLatency", 0),
                    kill_switch_active=risk_settings.kill_switch_enabled,
                )
                session.add(snapshot)
                await session.commit()
        except Exception as e:
            logger.error("worker.db_save_metrics_failed", error=str(e))

    async def _get_gas_balances(self) -> dict:
        """Fetch gas balances from all chains."""
        balances = {"polygon": 0.0, "arbitrum": 0.0, "solana": 0.0}
        try:
            balances["arbitrum"] = self.premu.get_gas_balance()
        except Exception:
            pass
        try:
            balances["solana"] = await self.monaco.get_sol_balance()
        except Exception:
            pass
        return balances


# ─── ENTRY POINT ──────────────────────────────────────────────────────────────

async def main():
    """Entry point for the worker process."""
    worker = ArbitrageWorker()
    await worker.start()


if __name__ == "__main__":
    print("=" * 60)
    print("  Cross-Market Arbitrage Bot — Worker Engine")
    print("=" * 60)
    asyncio.run(main())
