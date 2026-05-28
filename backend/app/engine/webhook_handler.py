"""
Webhook Handler — Ingests macroeconomic event data from external feeds.
Processes JSON payloads from Reuters, Bloomberg, TradingView, and custom sources.
"""

import hashlib
import hmac
import time
from typing import Optional

import structlog
from pydantic import BaseModel, Field

logger = structlog.get_logger(__name__)


class MacroEventPayload(BaseModel):
    """Standardized macroeconomic event payload."""
    event_type: str = Field(..., description="interest_rate, gdp, inflation, nfp, etc.")
    country: str = Field(..., description="ISO 3166-1 alpha-2 country code")
    headline: str = Field(..., description="Event headline/description")
    actual_value: Optional[str] = None
    forecast_value: Optional[str] = None
    previous_value: Optional[str] = None
    impact_level: str = Field(default="medium", description="high, medium, low")
    source: str = Field(default="custom", description="reuters, bloomberg, tradingview, custom")
    timestamp_ms: Optional[int] = None


class WebhookHandler:
    """
    Processes incoming webhook payloads from macroeconomic data feeds.
    Validates HMAC signatures, parses events, and routes to the arbitrage engine.
    """

    # Event types that are high-priority for immediate execution
    HIGH_PRIORITY_EVENTS = {
        "interest_rate",
        "inflation",
        "gdp",
        "nfp",  # Non-Farm Payrolls
        "unemployment",
        "central_bank_statement",
        "trade_balance",
    }

    # Country → Currency pair mapping for the MENA region
    COUNTRY_TO_PAIRS = {
        "US": ["EURUSD", "GBPUSD", "XAUUSD"],
        "GB": ["GBPUSD"],
        "EU": ["EURUSD"],
        "JP": ["USDJPY"],
        "SA": ["XAUUSD", "USOIL"],  # Saudi Arabia → Gold & Oil
        "AE": ["XAUUSD", "USOIL"],  # UAE → Gold & Oil
    }

    def __init__(self, on_event_processed=None):
        self.on_event_processed = on_event_processed
        self._processed_count = 0

    def validate_signature(self, payload: bytes, signature: str, secret: str) -> bool:
        """Validate HMAC-SHA256 signature on incoming webhook."""
        expected = hmac.new(
            secret.encode("utf-8"),
            payload,
            hashlib.sha256,
        ).hexdigest()
        return hmac.compare_digest(expected, signature)

    async def process_event(self, event: MacroEventPayload) -> dict:
        """
        Process a validated macro event.
        Returns routing info for the arbitrage engine.
        """
        if event.timestamp_ms is None:
            event.timestamp_ms = int(time.time() * 1000)

        # Determine urgency
        is_high_priority = event.event_type in self.HIGH_PRIORITY_EVENTS
        is_surprise = self._is_surprise(event)

        # Determine affected forex pairs
        affected_pairs = self.COUNTRY_TO_PAIRS.get(event.country, [])

        # Determine directional bias
        direction = self._infer_direction(event)

        result = {
            "event": event.model_dump(),
            "is_high_priority": is_high_priority,
            "is_surprise": is_surprise,
            "affected_pairs": affected_pairs,
            "inferred_direction": direction,
            "should_execute": is_high_priority and is_surprise,
            "processing_latency_ms": int(time.time() * 1000) - event.timestamp_ms,
        }

        logger.info(
            "webhook.event_processed",
            event_type=event.event_type,
            country=event.country,
            high_priority=is_high_priority,
            surprise=is_surprise,
            direction=direction,
        )

        self._processed_count += 1

        if self.on_event_processed:
            await self.on_event_processed(result)

        return result

    def _is_surprise(self, event: MacroEventPayload) -> bool:
        """Check if the actual value significantly deviates from forecast."""
        if not event.actual_value or not event.forecast_value:
            return True  # Assume surprise if data missing

        try:
            actual = float(event.actual_value.replace("%", "").replace(",", ""))
            forecast = float(event.forecast_value.replace("%", "").replace(",", ""))

            if forecast == 0:
                return actual != 0

            deviation_pct = abs(actual - forecast) / abs(forecast) * 100
            return deviation_pct > 10  # >10% deviation = surprise

        except (ValueError, TypeError):
            return True

    def _infer_direction(self, event: MacroEventPayload) -> str:
        """Infer directional impact from event data (simplified)."""
        if not event.actual_value or not event.forecast_value:
            return "neutral"

        try:
            actual = float(event.actual_value.replace("%", "").replace(",", ""))
            forecast = float(event.forecast_value.replace("%", "").replace(",", ""))

            if actual > forecast:
                # Better than expected
                if event.event_type in ("interest_rate", "inflation"):
                    return "bearish"  # Higher rates/inflation → risk-off
                return "bullish"
            elif actual < forecast:
                if event.event_type in ("interest_rate", "inflation"):
                    return "bullish"
                return "bearish"
            return "neutral"

        except (ValueError, TypeError):
            return "neutral"
