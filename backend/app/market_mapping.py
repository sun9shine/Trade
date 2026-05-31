"""
Market Mapping Loader — Reads and manages forex-to-prediction-market mappings.
"""

import json
import os
from pathlib import Path
from typing import Optional

import structlog

logger = structlog.get_logger(__name__)

MAPPING_FILE = Path(__file__).parent / "market_mapping.json"


class MarketMapping:
    """
    Manages the mapping between forex symbols and prediction market IDs
    across Polymarket, Premu, and Monaco Protocol.
    """

    def __init__(self, mapping_file: Optional[Path] = None):
        self._file = mapping_file or MAPPING_FILE
        self._data: dict = {}
        self._load()

    def _load(self):
        """Load mapping from JSON file."""
        try:
            with open(self._file, "r") as f:
                self._data = json.load(f)
            logger.info("market_mapping.loaded", symbols=len(self.forex_markets))
        except FileNotFoundError:
            logger.error("market_mapping.file_not_found", path=str(self._file))
            self._data = {}
        except json.JSONDecodeError as e:
            logger.error("market_mapping.parse_error", error=str(e))
            self._data = {}

    def reload(self):
        """Hot-reload mapping without restart."""
        self._load()

    @property
    def forex_markets(self) -> dict:
        """Get forex-to-prediction-market mappings."""
        return self._data.get("forex_to_prediction_markets", {})

    @property
    def macro_event_markets(self) -> dict:
        """Get macro-event-to-market mappings."""
        return self._data.get("macro_event_to_markets", {})

    @property
    def negative_risk_pools(self) -> list:
        """Get negative risk arbitrage pool configurations."""
        return self._data.get("negative_risk_pools", {}).get("markets", [])

    @property
    def platform_config(self) -> dict:
        """Get platform-specific configuration."""
        return self._data.get("platform_config", {})

    def get_target_markets_for_symbol(self, symbol: str) -> dict[str, dict]:
        """
        Get all prediction market targets for a forex symbol.
        Returns: {symbol: {platform, market_id, ...}}
        """
        market_info = self.forex_markets.get(symbol)
        if not market_info:
            return {}

        targets = {}
        for platform, config in market_info.items():
            market_id = config.get("market_id") or config.get("market_pk", "")
            if market_id and not market_id.startswith("REPLACE"):
                targets[symbol] = {
                    "platform": platform,
                    "market_id": market_id,
                    **config,
                }
        return targets

    def get_markets_for_event(self, event_type: str, country: str) -> dict:
        """Get prediction market IDs triggered by a macro event."""
        key = f"{event_type}_{country}"
        return self.macro_event_markets.get(key, {})

    def get_neg_risk_market_ids(self) -> dict[str, str]:
        """Get {platform: market_id} for all negative risk pools."""
        result = {}
        for pool in self.negative_risk_pools:
            platform = pool["platform"]
            market_id = pool["market_id"]
            if not market_id.startswith("REPLACE") and not market_id.startswith("0x_"):
                result[platform] = market_id
        return result

    def update_market_id(self, symbol: str, platform: str, market_id: str):
        """Update a market ID and persist to file."""
        if symbol in self._data.get("forex_to_prediction_markets", {}):
            if platform in self._data["forex_to_prediction_markets"][symbol]:
                if platform == "monaco":
                    self._data["forex_to_prediction_markets"][symbol][platform]["market_pk"] = market_id
                else:
                    self._data["forex_to_prediction_markets"][symbol][platform]["market_id"] = market_id
                self._save()
                logger.info("market_mapping.updated", symbol=symbol, platform=platform)

    def _save(self):
        """Persist current mapping to JSON file."""
        with open(self._file, "w") as f:
            json.dump(self._data, f, indent=2)


# Singleton instance
market_mapping = MarketMapping()
