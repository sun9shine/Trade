"""
Tests for the Webhook Handler — macro event processing.
"""

import pytest
from unittest.mock import AsyncMock

from app.engine.webhook_handler import WebhookHandler, MacroEventPayload


class TestWebhookHandler:
    """Tests for WebhookHandler class."""

    def setup_method(self):
        self.handler = WebhookHandler()

    # ─── EVENT CLASSIFICATION ─────────────────────────────────────────────────

    @pytest.mark.asyncio
    async def test_high_priority_event(self):
        """Interest rate event should be high priority."""
        event = MacroEventPayload(
            event_type="interest_rate",
            country="US",
            headline="Fed raises rates",
            actual_value="5.50%",
            forecast_value="5.25%",
            impact_level="high",
            source="reuters",
        )

        result = await self.handler.process_event(event)

        assert result["is_high_priority"] is True
        assert "EURUSD" in result["affected_pairs"]
        assert "XAUUSD" in result["affected_pairs"]

    @pytest.mark.asyncio
    async def test_low_priority_event(self):
        """Trade balance should not be in high priority set by default."""
        event = MacroEventPayload(
            event_type="consumer_confidence",
            country="US",
            headline="Consumer confidence rises",
            actual_value="105.0",
            forecast_value="103.5",
            impact_level="low",
            source="custom",
        )

        result = await self.handler.process_event(event)
        assert result["is_high_priority"] is False

    # ─── SURPRISE DETECTION ───────────────────────────────────────────────────

    @pytest.mark.asyncio
    async def test_surprise_detection_big_miss(self):
        """Big deviation from forecast should be a surprise."""
        event = MacroEventPayload(
            event_type="inflation",
            country="US",
            headline="CPI surges",
            actual_value="6.5%",
            forecast_value="5.0%",
            impact_level="high",
            source="reuters",
        )

        result = await self.handler.process_event(event)
        assert result["is_surprise"] is True

    @pytest.mark.asyncio
    async def test_no_surprise_inline(self):
        """Inline with forecast should not be a surprise."""
        event = MacroEventPayload(
            event_type="gdp",
            country="US",
            headline="GDP as expected",
            actual_value="2.5%",
            forecast_value="2.4%",
            impact_level="medium",
            source="bloomberg",
        )

        result = await self.handler.process_event(event)
        assert result["is_surprise"] is False

    @pytest.mark.asyncio
    async def test_surprise_missing_data(self):
        """Missing data should assume surprise (cautious approach)."""
        event = MacroEventPayload(
            event_type="interest_rate",
            country="EU",
            headline="ECB decision",
            impact_level="high",
            source="reuters",
        )

        result = await self.handler.process_event(event)
        assert result["is_surprise"] is True

    # ─── DIRECTION INFERENCE ──────────────────────────────────────────────────

    @pytest.mark.asyncio
    async def test_direction_higher_rate_bearish(self):
        """Higher than expected rates should be bearish (risk-off)."""
        event = MacroEventPayload(
            event_type="interest_rate",
            country="US",
            headline="Fed hikes",
            actual_value="5.75%",
            forecast_value="5.50%",
            impact_level="high",
            source="reuters",
        )

        result = await self.handler.process_event(event)
        assert result["inferred_direction"] == "bearish"

    @pytest.mark.asyncio
    async def test_direction_better_gdp_bullish(self):
        """Better than expected GDP should be bullish."""
        event = MacroEventPayload(
            event_type="gdp",
            country="US",
            headline="GDP beats",
            actual_value="3.5%",
            forecast_value="2.5%",
            impact_level="high",
            source="bloomberg",
        )

        result = await self.handler.process_event(event)
        assert result["inferred_direction"] == "bullish"

    # ─── COUNTRY MAPPING ──────────────────────────────────────────────────────

    @pytest.mark.asyncio
    async def test_country_pairs_us(self):
        """US events should affect EURUSD, GBPUSD, XAUUSD."""
        event = MacroEventPayload(
            event_type="nfp",
            country="US",
            headline="NFP data",
            actual_value="200K",
            forecast_value="180K",
            impact_level="high",
            source="reuters",
        )

        result = await self.handler.process_event(event)
        assert "EURUSD" in result["affected_pairs"]
        assert "GBPUSD" in result["affected_pairs"]

    @pytest.mark.asyncio
    async def test_country_pairs_saudi(self):
        """Saudi events should affect Gold and Oil."""
        event = MacroEventPayload(
            event_type="trade_balance",
            country="SA",
            headline="Saudi oil output",
            impact_level="high",
            source="custom",
        )

        result = await self.handler.process_event(event)
        assert "XAUUSD" in result["affected_pairs"]
        assert "USOIL" in result["affected_pairs"]

    # ─── EXECUTION DECISION ───────────────────────────────────────────────────

    @pytest.mark.asyncio
    async def test_should_execute_high_priority_surprise(self):
        """Should execute only if high priority AND surprise."""
        event = MacroEventPayload(
            event_type="interest_rate",
            country="US",
            headline="Fed surprises",
            actual_value="6.0%",
            forecast_value="5.25%",
            impact_level="high",
            source="reuters",
        )

        result = await self.handler.process_event(event)
        assert result["should_execute"] is True

    @pytest.mark.asyncio
    async def test_should_not_execute_low_priority(self):
        """Low priority events should not trigger execution."""
        event = MacroEventPayload(
            event_type="consumer_confidence",
            country="US",
            headline="Consumer survey",
            actual_value="110",
            forecast_value="100",
            impact_level="low",
            source="custom",
        )

        result = await self.handler.process_event(event)
        assert result["should_execute"] is False

    # ─── CALLBACK ─────────────────────────────────────────────────────────────

    @pytest.mark.asyncio
    async def test_callback_invoked(self):
        """on_event_processed callback should be called."""
        callback = AsyncMock()
        handler = WebhookHandler(on_event_processed=callback)

        event = MacroEventPayload(
            event_type="gdp",
            country="US",
            headline="GDP data",
            impact_level="medium",
            source="custom",
        )

        await handler.process_event(event)
        callback.assert_called_once()
