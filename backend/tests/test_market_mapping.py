"""
Tests for market mapping loader.
"""

import json
import tempfile
from pathlib import Path
import pytest

from app.market_mapping import MarketMapping


class TestMarketMapping:
    """Tests for MarketMapping class."""

    def setup_method(self):
        """Create a temporary mapping file for testing."""
        self.test_data = {
            "version": "1.0.0",
            "forex_to_prediction_markets": {
                "EURUSD": {
                    "polymarket": {
                        "market_id": "0xreal_market_id",
                        "market_title": "EUR/USD test",
                    },
                    "premu": {
                        "market_id": "abc123hex",
                        "asset_label": "EUR/USD",
                    },
                },
                "XAUUSD": {
                    "monaco": {
                        "market_pk": "SolanaMarketPubkey123",
                        "market_title": "Gold direction",
                    },
                },
            },
            "macro_event_to_markets": {
                "interest_rate_US": {
                    "polymarket": ["0xfed_market"],
                    "affected_forex": ["EURUSD"],
                },
            },
            "negative_risk_pools": {
                "markets": [
                    {
                        "platform": "polymarket",
                        "market_id": "0xreal_neg_risk",
                        "title": "Multi-outcome test",
                        "outcome_count": 3,
                    },
                ]
            },
            "platform_config": {
                "polymarket": {"chain": "polygon", "min_order_size": 1.0},
            },
        }

        self.tmp_file = tempfile.NamedTemporaryFile(
            mode="w", suffix=".json", delete=False
        )
        json.dump(self.test_data, self.tmp_file)
        self.tmp_file.close()

        self.mapping = MarketMapping(Path(self.tmp_file.name))

    def test_loads_forex_markets(self):
        assert "EURUSD" in self.mapping.forex_markets
        assert "XAUUSD" in self.mapping.forex_markets

    def test_get_target_markets_for_symbol(self):
        targets = self.mapping.get_target_markets_for_symbol("EURUSD")
        assert "EURUSD" in targets
        assert targets["EURUSD"]["platform"] == "polymarket"

    def test_get_target_markets_nonexistent(self):
        targets = self.mapping.get_target_markets_for_symbol("INVALID")
        assert targets == {}

    def test_get_markets_for_event(self):
        markets = self.mapping.get_markets_for_event("interest_rate", "US")
        assert "polymarket" in markets

    def test_negative_risk_pools(self):
        pools = self.mapping.negative_risk_pools
        assert len(pools) == 1
        assert pools[0]["platform"] == "polymarket"

    def test_platform_config(self):
        config = self.mapping.platform_config
        assert "polymarket" in config
        assert config["polymarket"]["chain"] == "polygon"

    def test_reload(self):
        """Hot reload should re-read the file."""
        self.mapping.reload()
        assert "EURUSD" in self.mapping.forex_markets
