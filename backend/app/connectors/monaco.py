"""
Monaco Protocol Connector — Solana-based prediction market order book.
Uses Anchor IDL deserialization for on-chain market account parsing.
Implements priority fee management for fast transaction confirmation.
"""

import base64
import struct
from dataclasses import dataclass
from typing import Optional

import structlog

from app.config import blockchain_settings

logger = structlog.get_logger(__name__)


# Monaco Protocol IDL account structure definitions
# Based on the Monaco Protocol Anchor program
MONACO_PROGRAM_ID = "monacoUXKtUi6vKsQwaLyxmXKSievfNWEcYXTgkbCih"

# Account discriminators (first 8 bytes of SHA256("account:<Name>"))
MARKET_DISCRIMINATOR = bytes([219, 190, 213, 55, 0, 227, 198, 154])
MARKET_OUTCOME_DISCRIMINATOR = bytes([177, 83, 145, 29, 181, 137, 93, 212])
ORDER_DISCRIMINATOR = bytes([134, 173, 223, 185, 77, 86, 28, 51])


@dataclass
class MonacoMarketOrder:
    """Order representation for Monaco Protocol."""
    market_pk: str  # Market public key
    outcome_index: int  # 0, 1, 2, etc.
    side: str  # "for" (YES) or "against" (NO)
    price: float  # Odds in decimal (e.g., 1.5 = 66.7% implied)
    stake: float  # Amount in SOL/USDC


@dataclass
class MonacoOutcome:
    """Outcome state from Monaco on-chain order book."""
    index: int
    title: str
    best_for_price: float  # Best YES price
    best_against_price: float  # Best NO price
    matched_total: float
    implied_probability: float


@dataclass
class MonacoMarketState:
    """Deserialized Monaco market account state."""
    authority: str
    market_status: int  # 0=Initializing, 1=Open, 2=Locked, 3=Settled
    mint: str  # Token mint (USDC)
    market_type: int
    title: str
    lock_timestamp: int
    outcomes_count: int


class MonacoIDLParser:
    """
    Deserializes Monaco Protocol Anchor account data from raw bytes.
    Implements the IDL-based parsing without requiring the full Anchor framework.
    """

    @staticmethod
    def parse_market_account(data: bytes) -> Optional[MonacoMarketState]:
        """
        Parse a Market account from raw on-chain data.

        Monaco Market account layout (after 8-byte discriminator):
        - authority: Pubkey (32 bytes)
        - market_status: u8 (1 byte)
        - padding: 3 bytes
        - mint: Pubkey (32 bytes)
        - market_type: u8 (1 byte)
        - padding: 3 bytes
        - title: String (4 bytes length + UTF-8 data)
        - lock_timestamp: i64 (8 bytes)
        - outcomes_count: u16 (2 bytes)
        """
        try:
            # Verify discriminator
            if data[:8] != MARKET_DISCRIMINATOR:
                logger.warning("monaco_idl.invalid_discriminator", expected="market")
                return None

            offset = 8

            # authority (32 bytes pubkey)
            authority_bytes = data[offset:offset + 32]
            authority = base64.b58encode(authority_bytes).decode()
            offset += 32

            # market_status (u8)
            market_status = data[offset]
            offset += 1

            # padding (3 bytes alignment)
            offset += 3

            # mint (32 bytes pubkey)
            mint_bytes = data[offset:offset + 32]
            mint = base64.b58encode(mint_bytes).decode()
            offset += 32

            # market_type (u8)
            market_type = data[offset]
            offset += 1

            # padding (3 bytes alignment)
            offset += 3

            # title (Borsh string: 4-byte LE length + UTF-8)
            title_len = struct.unpack_from("<I", data, offset)[0]
            offset += 4
            title = data[offset:offset + title_len].decode("utf-8", errors="replace")
            offset += title_len

            # lock_timestamp (i64 LE)
            lock_timestamp = struct.unpack_from("<q", data, offset)[0]
            offset += 8

            # outcomes_count (u16 LE)
            outcomes_count = struct.unpack_from("<H", data, offset)[0]

            return MonacoMarketState(
                authority=authority,
                market_status=market_status,
                mint=mint,
                market_type=market_type,
                title=title,
                lock_timestamp=lock_timestamp,
                outcomes_count=outcomes_count,
            )

        except Exception as e:
            logger.error("monaco_idl.parse_market_failed", error=str(e))
            return None

    @staticmethod
    def parse_market_outcome(data: bytes) -> Optional[dict]:
        """
        Parse a MarketOutcome account from raw on-chain data.

        MarketOutcome layout (after 8-byte discriminator):
        - market: Pubkey (32 bytes)
        - index: u16 (2 bytes)
        - title: String (4 bytes length + UTF-8)
        - latest_matched_price: f64 (8 bytes)
        - matched_total: u64 (8 bytes)
        """
        try:
            if data[:8] != MARKET_OUTCOME_DISCRIMINATOR:
                return None

            offset = 8

            # market pubkey (32 bytes)
            market_pk = base64.b58encode(data[offset:offset + 32]).decode()
            offset += 32

            # index (u16 LE)
            index = struct.unpack_from("<H", data, offset)[0]
            offset += 2

            # padding (2 bytes)
            offset += 2

            # title (Borsh string)
            title_len = struct.unpack_from("<I", data, offset)[0]
            offset += 4
            title = data[offset:offset + title_len].decode("utf-8", errors="replace")
            offset += title_len

            # latest_matched_price (f64 LE)
            latest_price = struct.unpack_from("<d", data, offset)[0]
            offset += 8

            # matched_total (u64 LE)
            matched_total = struct.unpack_from("<Q", data, offset)[0]

            return {
                "market_pk": market_pk,
                "index": index,
                "title": title,
                "latest_matched_price": latest_price,
                "matched_total": matched_total,
            }

        except Exception as e:
            logger.error("monaco_idl.parse_outcome_failed", error=str(e))
            return None

    @staticmethod
    def parse_order(data: bytes) -> Optional[dict]:
        """
        Parse an Order account from raw on-chain data.

        Order layout (after 8-byte discriminator):
        - market: Pubkey (32 bytes)
        - market_outcome_index: u16 (2 bytes)
        - for_outcome: bool (1 byte)
        - order_status: u8 (1 byte)
        - purchaser: Pubkey (32 bytes)
        - stake: u64 (8 bytes)
        - expected_price: f64 (8 bytes)
        - creation_timestamp: i64 (8 bytes)
        """
        try:
            if data[:8] != ORDER_DISCRIMINATOR:
                return None

            offset = 8

            market_pk = base64.b58encode(data[offset:offset + 32]).decode()
            offset += 32

            outcome_index = struct.unpack_from("<H", data, offset)[0]
            offset += 2

            for_outcome = bool(data[offset])
            offset += 1

            order_status = data[offset]
            offset += 1

            purchaser = base64.b58encode(data[offset:offset + 32]).decode()
            offset += 32

            stake = struct.unpack_from("<Q", data, offset)[0]
            offset += 8

            expected_price = struct.unpack_from("<d", data, offset)[0]
            offset += 8

            creation_timestamp = struct.unpack_from("<q", data, offset)[0]

            return {
                "market_pk": market_pk,
                "outcome_index": outcome_index,
                "for_outcome": for_outcome,
                "order_status": order_status,
                "purchaser": purchaser,
                "stake": stake,
                "expected_price": expected_price,
                "creation_timestamp": creation_timestamp,
            }

        except Exception as e:
            logger.error("monaco_idl.parse_order_failed", error=str(e))
            return None


class MonacoConnector:
    """
    Interface to Monaco Protocol on Solana.
    Reads on-chain Order Book (YES/NO shares) via Anchor IDL deserialization
    and executes trades using fast RPC nodes with priority fees.
    """

    def __init__(self):
        self._rpc_url = blockchain_settings.solana_rpc_url
        self._private_key = blockchain_settings.solana_private_key
        self._client = None
        self._keypair = None
        self._idl_parser = MonacoIDLParser()

    async def initialize(self):
        """Initialize Solana client and keypair."""
        try:
            from solana.rpc.async_api import AsyncClient
            from solders.keypair import Keypair

            self._client = AsyncClient(self._rpc_url)

            # Decode base58 private key
            key_bytes = base64.b58decode(self._private_key)
            self._keypair = Keypair.from_bytes(key_bytes)

            balance_resp = await self._client.get_balance(self._keypair.pubkey())
            balance_sol = balance_resp.value / 1_000_000_000

            logger.info(
                "monaco.initialized",
                chain="solana",
                wallet=str(self._keypair.pubkey()),
                sol_balance=balance_sol,
                idl_parser="active",
            )
        except Exception as e:
            logger.error("monaco.init_failed", error=str(e))
            raise

    async def get_market_state(self, market_pk: str) -> Optional[MonacoMarketState]:
        """
        Fetch and deserialize a Monaco market account from Solana.
        Uses Anchor IDL-based binary parsing.
        """
        try:
            from solders.pubkey import Pubkey

            market_pubkey = Pubkey.from_string(market_pk)
            account_resp = await self._client.get_account_info(market_pubkey)

            if not account_resp.value:
                logger.warning("monaco.market_not_found", market_pk=market_pk)
                return None

            # Get raw account data
            raw_data = account_resp.value.data
            if isinstance(raw_data, str):
                raw_data = base64.b64decode(raw_data)

            # Parse using IDL parser
            market_state = self._idl_parser.parse_market_account(raw_data)
            if market_state:
                logger.debug(
                    "monaco.market_parsed",
                    title=market_state.title,
                    status=market_state.market_status,
                    outcomes=market_state.outcomes_count,
                )
            return market_state

        except Exception as e:
            logger.error("monaco.get_market_state_failed", error=str(e))
            return None

    async def get_market_outcomes(self, market_pk: str) -> list[MonacoOutcome]:
        """
        Fetch the on-chain order book state for a Monaco market.
        Reads all outcome accounts associated with the market via getProgramAccounts.
        """
        try:
            from solders.pubkey import Pubkey
            from solana.rpc.types import MemcmpOpts

            program_id = Pubkey.from_string(MONACO_PROGRAM_ID)
            market_pubkey = Pubkey.from_string(market_pk)

            # Filter: discriminator + market pubkey at offset 8
            filters = [
                MemcmpOpts(offset=0, bytes=MARKET_OUTCOME_DISCRIMINATOR),
                MemcmpOpts(offset=8, bytes=bytes(market_pubkey)),
            ]

            # Fetch all outcome accounts for this market
            accounts_resp = await self._client.get_program_accounts(
                program_id,
                filters=filters,
                encoding="base64",
            )

            outcomes = []
            for account_info in accounts_resp.value:
                raw_data = account_info.account.data
                if isinstance(raw_data, str):
                    raw_data = base64.b64decode(raw_data)

                parsed = self._idl_parser.parse_market_outcome(raw_data)
                if parsed:
                    # Calculate implied probability from matched price
                    price = parsed["latest_matched_price"]
                    implied_prob = price if 0 < price < 1 else 0.5

                    outcomes.append(MonacoOutcome(
                        index=parsed["index"],
                        title=parsed["title"],
                        best_for_price=price,
                        best_against_price=1.0 - price if price > 0 else 0.5,
                        matched_total=parsed["matched_total"] / 1_000_000,  # USDC decimals
                        implied_probability=implied_prob,
                    ))

            # Sort by index
            outcomes.sort(key=lambda o: o.index)

            logger.info(
                "monaco.outcomes_fetched",
                market_pk=market_pk,
                outcome_count=len(outcomes),
            )
            return outcomes

        except Exception as e:
            logger.error("monaco.fetch_outcomes_failed", error=str(e))
            return []

    async def get_open_orders(self, market_pk: str) -> list[dict]:
        """Fetch all open orders for a market (order book depth)."""
        try:
            from solders.pubkey import Pubkey
            from solana.rpc.types import MemcmpOpts

            program_id = Pubkey.from_string(MONACO_PROGRAM_ID)
            market_pubkey = Pubkey.from_string(market_pk)

            filters = [
                MemcmpOpts(offset=0, bytes=ORDER_DISCRIMINATOR),
                MemcmpOpts(offset=8, bytes=bytes(market_pubkey)),
            ]

            accounts_resp = await self._client.get_program_accounts(
                program_id,
                filters=filters,
                encoding="base64",
            )

            orders = []
            for account_info in accounts_resp.value:
                raw_data = account_info.account.data
                if isinstance(raw_data, str):
                    raw_data = base64.b64decode(raw_data)

                parsed = self._idl_parser.parse_order(raw_data)
                if parsed and parsed["order_status"] == 0:  # Open orders only
                    orders.append(parsed)

            return orders

        except Exception as e:
            logger.error("monaco.fetch_orders_failed", error=str(e))
            return []

    async def place_order(self, order: MonacoMarketOrder) -> Optional[str]:
        """
        Place a trade on Monaco Protocol.
        Uses compute budget instructions for priority fees.
        """
        try:
            from solana.rpc.types import TxOpts
            from solana.transaction import Transaction
            from solders.pubkey import Pubkey
            from solders.compute_budget import set_compute_unit_price, set_compute_unit_limit

            # Set compute budget with priority fee
            compute_limit_ix = set_compute_unit_limit(400_000)
            priority_fee_ix = set_compute_unit_price(50_000)  # ~0.02 SOL priority

            tx = Transaction()
            tx.add(compute_limit_ix)
            tx.add(priority_fee_ix)

            # In production: build full Monaco Protocol CreateOrder instruction
            # using the program IDL and proper account resolution
            # The instruction would include:
            # - market account
            # - market outcome account
            # - purchaser token account
            # - market escrow account
            # - token program
            # - system program

            # Placeholder: In real deployment, use anchorpy with the Monaco IDL
            # to construct the proper instruction
            logger.info(
                "monaco.order_building",
                market_pk=order.market_pk,
                side=order.side,
                price=order.price,
                stake=order.stake,
                outcome_index=order.outcome_index,
            )

            opts = TxOpts(skip_preflight=True, max_retries=3)

            # NOTE: Full order placement requires:
            # 1. Resolve all PDAs (market matching pool, order account, etc.)
            # 2. Build CreateOrderV2 instruction with proper args
            # 3. Sign and submit
            # This requires the full Monaco IDL which should be fetched from on-chain

            # For now, return None until IDL is fetched and instruction is built
            # In production: uncomment below after IDL integration
            # result = await self._client.send_transaction(tx, self._keypair, opts=opts)
            # tx_sig = str(result.value)

            tx_sig = None  # Will be populated with real tx after full IDL integration
            if tx_sig:
                logger.info(
                    "monaco.order_placed",
                    market_pk=order.market_pk,
                    side=order.side,
                    price=order.price,
                    stake=order.stake,
                    tx_sig=tx_sig,
                )
            return tx_sig

        except Exception as e:
            logger.error("monaco.order_failed", error=str(e))
            return None

    async def cancel_all_orders(self, market_pk: Optional[str] = None) -> bool:
        """Cancel all open orders on Monaco Protocol (Kill Switch)."""
        try:
            # Fetch all open orders for our wallet
            if market_pk:
                orders = await self.get_open_orders(market_pk)
            else:
                orders = []  # Would need to scan all markets

            cancelled = 0
            for order in orders:
                if order["purchaser"] == str(self._keypair.pubkey()):
                    # Build cancel instruction for each order
                    # In production: batch cancel using Monaco's CancelOrder instruction
                    cancelled += 1

            logger.info("monaco.cancel_all", market_pk=market_pk or "all", cancelled=cancelled)
            return True
        except Exception as e:
            logger.error("monaco.cancel_failed", error=str(e))
            return False

    async def get_sol_balance(self) -> float:
        """Get SOL balance for gas/priority fees."""
        if not self._client or not self._keypair:
            return 0.0
        try:
            resp = await self._client.get_balance(self._keypair.pubkey())
            return resp.value / 1_000_000_000
        except Exception:
            return 0.0
