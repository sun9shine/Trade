"""
Polymarket V2 Connector — CLOB API integration with EIP-712 signing.
Uses pUSD collateral (backed 1:1 with USDC on Polygon).
"""

import time
from dataclasses import dataclass
from typing import Optional

import structlog
from web3 import Web3

from app.config import blockchain_settings

logger = structlog.get_logger(__name__)


@dataclass
class PolymarketOrder:
    """Order structure for Polymarket CLOB."""
    token_id: str  # Condition token ID (YES or NO share)
    side: str  # "BUY" or "SELL"
    price: float  # 0.01 to 0.99 (implied probability)
    size: float  # Number of shares
    order_type: str = "GTC"  # GTC, FOK, IOC


@dataclass
class MarketOutcome:
    """Represents odds for a single outcome on Polymarket."""
    token_id: str
    outcome_label: str
    best_bid: float
    best_ask: float
    implied_probability: float


class PolymarketConnector:
    """
    Interface to Polymarket V2 architecture:
    - Central Limit Order Book (CLOB) API
    - EIP-712 typed signatures for order placement
    - pUSD collateral management
    """

    CLOB_API_BASE = "https://clob.polymarket.com"
    GAMMA_API_BASE = "https://gamma-api.polymarket.com"

    def __init__(self):
        self.w3 = Web3(Web3.HTTPProvider(blockchain_settings.polygon_rpc_url))
        self._api_key = blockchain_settings.polymarket_api_key
        self._api_secret = blockchain_settings.polymarket_api_secret
        self._passphrase = blockchain_settings.polymarket_passphrase
        self._private_key = blockchain_settings.polygon_private_key
        self._client = None

    async def initialize(self):
        """Initialize the py-clob-client connection."""
        try:
            from py_clob_client.client import ClobClient
            from py_clob_client.clob_types import ApiCreds

            creds = ApiCreds(
                api_key=self._api_key,
                api_secret=self._api_secret,
                api_passphrase=self._passphrase,
            )

            self._client = ClobClient(
                host=self.CLOB_API_BASE,
                key=self._private_key,
                chain_id=137,  # Polygon mainnet
                creds=creds,
            )

            logger.info("polymarket.initialized", chain="polygon")
        except Exception as e:
            logger.error("polymarket.init_failed", error=str(e))
            raise

    async def get_market_odds(self, condition_id: str) -> list[MarketOutcome]:
        """
        Fetch current order book state for a binary market.
        Returns best bid/ask for YES and NO tokens.
        """
        import httpx

        url = f"{self.CLOB_API_BASE}/book"
        params = {"token_id": condition_id}

        async with httpx.AsyncClient() as client:
            response = await client.get(url, params=params)
            response.raise_for_status()
            data = response.json()

        outcomes = []
        for side_data in data.get("market", {}).get("tokens", []):
            token_id = side_data["token_id"]
            outcome_label = side_data["outcome"]
            bids = side_data.get("bids", [])
            asks = side_data.get("asks", [])

            best_bid = float(bids[0]["price"]) if bids else 0.0
            best_ask = float(asks[0]["price"]) if asks else 1.0

            outcomes.append(MarketOutcome(
                token_id=token_id,
                outcome_label=outcome_label,
                best_bid=best_bid,
                best_ask=best_ask,
                implied_probability=(best_bid + best_ask) / 2,
            ))

        return outcomes

    async def place_order(self, order: PolymarketOrder) -> Optional[str]:
        """
        Place an order on Polymarket CLOB with EIP-712 signature.
        Returns order_id on success.
        """
        if not self._client:
            await self.initialize()

        try:
            from py_clob_client.clob_types import OrderArgs, OrderType

            order_type_map = {
                "GTC": OrderType.GTC,
                "FOK": OrderType.FOK,
                "IOC": OrderType.IOC,
            }

            order_args = OrderArgs(
                token_id=order.token_id,
                price=order.price,
                size=order.size,
                side=order.side,
            )

            signed_order = self._client.create_order(order_args)
            result = self._client.post_order(signed_order, order_type_map[order.order_type])

            order_id = result.get("orderID")
            logger.info(
                "polymarket.order_placed",
                order_id=order_id,
                token_id=order.token_id,
                side=order.side,
                price=order.price,
                size=order.size,
            )
            return order_id

        except Exception as e:
            logger.error("polymarket.order_failed", error=str(e))
            return None

    async def cancel_all_orders(self):
        """Cancel all open orders (Kill Switch support)."""
        if not self._client:
            return
        try:
            self._client.cancel_all()
            logger.info("polymarket.all_orders_cancelled")
        except Exception as e:
            logger.error("polymarket.cancel_failed", error=str(e))

    def get_total_implied_probability(self, outcomes: list[MarketOutcome]) -> float:
        """Calculate total implied probability across all outcomes."""
        return sum(o.implied_probability for o in outcomes)
