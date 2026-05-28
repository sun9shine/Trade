"""
Forex Data Ingestion Engine — MetaTrader 5 & OANDA WebSocket connections.
Streams real-time tick data for EUR/USD, GBP/USD, XAU/USD, and Oil (WTI).
"""

import asyncio
import time
from dataclasses import dataclass
from typing import Callable, Optional

import numpy as np
import structlog

from app.config import forex_settings

logger = structlog.get_logger(__name__)

WATCHED_SYMBOLS = ["EURUSD", "GBPUSD", "XAUUSD", "USOIL"]


@dataclass
class TickData:
    """Normalized tick data structure."""
    symbol: str
    bid: float
    ask: float
    spread: float
    source: str  # "mt5" or "oanda"
    timestamp_ms: int


class ForexEngine:
    """
    High-speed forex tick ingestion engine.
    Supports MetaTrader 5 SDK and OANDA v20 streaming API.
    """

    def __init__(self, on_tick: Optional[Callable] = None, on_anomaly: Optional[Callable] = None):
        self.on_tick = on_tick
        self.on_anomaly = on_anomaly
        self._running = False
        self._tick_buffer: dict[str, list[float]] = {s: [] for s in WATCHED_SYMBOLS}
        self._buffer_window = 50  # Last N ticks for anomaly detection
        self._anomaly_threshold_pct = 1.5  # Trigger if >1.5% move in window

    async def start_mt5_stream(self):
        """
        Connect to MetaTrader 5 and stream tick data.
        Requires MT5 terminal running (Windows) or remote bridge.
        """
        try:
            import MetaTrader5 as mt5

            if not mt5.initialize(
                login=int(forex_settings.mt5_login),
                password=forex_settings.mt5_password,
                server=forex_settings.mt5_server,
            ):
                logger.error("mt5.initialize_failed", error=mt5.last_error())
                return

            logger.info("mt5.connected", server=forex_settings.mt5_server)
            self._running = True

            while self._running:
                for symbol in WATCHED_SYMBOLS:
                    tick = mt5.symbol_info_tick(symbol)
                    if tick is None:
                        continue

                    tick_data = TickData(
                        symbol=symbol,
                        bid=tick.bid,
                        ask=tick.ask,
                        spread=round(tick.ask - tick.bid, 6),
                        source="mt5",
                        timestamp_ms=int(tick.time_msc),
                    )

                    await self._process_tick(tick_data)

                await asyncio.sleep(0.01)  # 10ms polling loop

        except ImportError:
            logger.warning("mt5.not_available", msg="MetaTrader5 SDK not installed")
        except Exception as e:
            logger.error("mt5.stream_error", error=str(e))
        finally:
            self._running = False

    async def start_oanda_stream(self):
        """
        Connect to OANDA v20 streaming API via WebSocket.
        """
        import httpx

        base_url = (
            "https://stream-fxpractice.oanda.com"
            if forex_settings.oanda_environment == "practice"
            else "https://stream-fxtrade.oanda.com"
        )

        instruments = ",".join(WATCHED_SYMBOLS)
        url = f"{base_url}/v3/accounts/{forex_settings.oanda_account_id}/pricing/stream"
        headers = {"Authorization": f"Bearer {forex_settings.oanda_api_key}"}
        params = {"instruments": instruments}

        logger.info("oanda.connecting", url=url)
        self._running = True

        try:
            async with httpx.AsyncClient(timeout=None) as client:
                async with client.stream("GET", url, headers=headers, params=params) as response:
                    async for line in response.aiter_lines():
                        if not self._running:
                            break
                        if not line:
                            continue

                        import orjson
                        data = orjson.loads(line)

                        if data.get("type") != "PRICE":
                            continue

                        symbol = data["instrument"].replace("_", "")
                        bid = float(data["bids"][0]["price"])
                        ask = float(data["asks"][0]["price"])

                        tick_data = TickData(
                            symbol=symbol,
                            bid=bid,
                            ask=ask,
                            spread=round(ask - bid, 6),
                            source="oanda",
                            timestamp_ms=int(time.time() * 1000),
                        )

                        await self._process_tick(tick_data)

        except Exception as e:
            logger.error("oanda.stream_error", error=str(e))
        finally:
            self._running = False

    async def _process_tick(self, tick: TickData):
        """Process incoming tick — buffer, detect anomalies, and dispatch."""
        # Fire tick callback
        if self.on_tick:
            await self.on_tick(tick)

        # Update rolling buffer
        mid_price = (tick.bid + tick.ask) / 2
        buffer = self._tick_buffer[tick.symbol]
        buffer.append(mid_price)

        if len(buffer) > self._buffer_window:
            buffer.pop(0)

        # Anomaly detection: check for sudden spike
        if len(buffer) >= 10:
            recent_mean = np.mean(buffer[-10:])
            baseline_mean = np.mean(buffer[:-10]) if len(buffer) > 10 else recent_mean

            if baseline_mean > 0:
                pct_change = abs(recent_mean - baseline_mean) / baseline_mean * 100

                if pct_change >= self._anomaly_threshold_pct:
                    logger.warning(
                        "forex.anomaly_detected",
                        symbol=tick.symbol,
                        pct_change=round(pct_change, 3),
                        direction="up" if recent_mean > baseline_mean else "down",
                    )
                    if self.on_anomaly:
                        await self.on_anomaly(tick, pct_change)

    def stop(self):
        """Gracefully stop all streams."""
        self._running = False
        logger.info("forex_engine.stopped")
