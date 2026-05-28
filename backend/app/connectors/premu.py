"""
Premu.xyz Connector — Arbitrum Fast Markets (5-minute up/down outcomes).
Uses ERC-2612 permit standard for single-signature instant execution.
"""

from dataclasses import dataclass
from typing import Optional

import structlog
from web3 import Web3
from web3.middleware import geth_poa_middleware
from eth_account import Account

from app.config import blockchain_settings

logger = structlog.get_logger(__name__)


# Premu Vault ABI (minimal interface for trading)
PREMU_VAULT_ABI = [
    {
        "inputs": [
            {"name": "marketId", "type": "bytes32"},
            {"name": "outcome", "type": "uint8"},
            {"name": "amount", "type": "uint256"},
            {"name": "deadline", "type": "uint256"},
            {"name": "v", "type": "uint8"},
            {"name": "r", "type": "bytes32"},
            {"name": "s", "type": "bytes32"},
        ],
        "name": "buyWithPermit",
        "outputs": [{"name": "shares", "type": "uint256"}],
        "stateMutability": "nonpayable",
        "type": "function",
    },
    {
        "inputs": [{"name": "marketId", "type": "bytes32"}],
        "name": "getMarketOdds",
        "outputs": [
            {"name": "upOdds", "type": "uint256"},
            {"name": "downOdds", "type": "uint256"},
            {"name": "expiresAt", "type": "uint256"},
        ],
        "stateMutability": "view",
        "type": "function",
    },
    {
        "inputs": [{"name": "marketId", "type": "bytes32"}],
        "name": "getMarketStatus",
        "outputs": [{"name": "status", "type": "uint8"}],
        "stateMutability": "view",
        "type": "function",
    },
    {
        "inputs": [],
        "name": "cancelAllPositions",
        "outputs": [],
        "stateMutability": "nonpayable",
        "type": "function",
    },
]


@dataclass
class PremuMarket:
    """Fast Market data from Premu."""
    market_id: bytes
    asset: str  # e.g., "BTC/USD", "ETH/USD"
    up_odds: float  # Probability for UP outcome (0-1)
    down_odds: float  # Probability for DOWN outcome (0-1)
    expires_at: int  # Unix timestamp
    status: int  # 0=open, 1=locked, 2=settled


class PremuConnector:
    """
    Interface to Premu.xyz on Arbitrum.
    Targets 5-minute Fast Markets with ERC-2612 permit execution.
    """

    def __init__(self):
        self.w3 = Web3(Web3.HTTPProvider(blockchain_settings.arbitrum_rpc_url))
        self.w3.middleware_onion.inject(geth_poa_middleware, layer=0)

        self._private_key = blockchain_settings.arbitrum_private_key
        self._account = None
        self._vault_contract = None

    async def initialize(self):
        """Initialize Web3 connection and vault contract."""
        try:
            self._account = Account.from_key(self._private_key)
            vault_address = Web3.to_checksum_address(blockchain_settings.premu_vault_address)

            self._vault_contract = self.w3.eth.contract(
                address=vault_address,
                abi=PREMU_VAULT_ABI,
            )

            balance = self.w3.eth.get_balance(self._account.address)
            logger.info(
                "premu.initialized",
                chain="arbitrum",
                wallet=self._account.address,
                eth_balance=Web3.from_wei(balance, "ether"),
            )
        except Exception as e:
            logger.error("premu.init_failed", error=str(e))
            raise

    async def get_fast_market(self, market_id: bytes) -> Optional[PremuMarket]:
        """Fetch current odds for a 5-minute Fast Market."""
        try:
            odds = self._vault_contract.functions.getMarketOdds(market_id).call()
            status = self._vault_contract.functions.getMarketStatus(market_id).call()

            # Odds returned as basis points (10000 = 100%)
            up_odds = odds[0] / 10000
            down_odds = odds[1] / 10000
            expires_at = odds[2]

            return PremuMarket(
                market_id=market_id,
                asset="",  # Resolved externally
                up_odds=up_odds,
                down_odds=down_odds,
                expires_at=expires_at,
                status=status,
            )
        except Exception as e:
            logger.error("premu.get_market_failed", error=str(e))
            return None

    async def buy_outcome_with_permit(
        self,
        market_id: bytes,
        outcome: int,  # 0 = UP, 1 = DOWN
        amount_wei: int,
    ) -> Optional[str]:
        """
        Execute a buy using ERC-2612 permit (gasless approval).
        Single-signature instant execution flow.
        """
        try:
            import time

            deadline = int(time.time()) + 300  # 5 minutes

            # Sign ERC-2612 permit (simplified — full impl requires domain separator)
            # In production: generate proper EIP-712 permit signature
            v, r, s = 27, b"\x00" * 32, b"\x00" * 32  # Placeholder

            tx = self._vault_contract.functions.buyWithPermit(
                market_id, outcome, amount_wei, deadline, v, r, s
            ).build_transaction({
                "from": self._account.address,
                "nonce": self.w3.eth.get_transaction_count(self._account.address),
                "gas": 300000,
                "gasPrice": self.w3.eth.gas_price,
                "chainId": 42161,  # Arbitrum One
            })

            signed_tx = self.w3.eth.account.sign_transaction(tx, self._private_key)
            tx_hash = self.w3.eth.send_raw_transaction(signed_tx.raw_transaction)

            logger.info(
                "premu.order_executed",
                market_id=market_id.hex(),
                outcome="UP" if outcome == 0 else "DOWN",
                amount_wei=amount_wei,
                tx_hash=tx_hash.hex(),
            )
            return tx_hash.hex()

        except Exception as e:
            logger.error("premu.buy_failed", error=str(e))
            return None

    async def cancel_all_positions(self) -> bool:
        """Cancel all open positions (Kill Switch)."""
        try:
            tx = self._vault_contract.functions.cancelAllPositions().build_transaction({
                "from": self._account.address,
                "nonce": self.w3.eth.get_transaction_count(self._account.address),
                "gas": 200000,
                "gasPrice": self.w3.eth.gas_price,
                "chainId": 42161,
            })
            signed_tx = self.w3.eth.account.sign_transaction(tx, self._private_key)
            tx_hash = self.w3.eth.send_raw_transaction(signed_tx.raw_transaction)
            logger.info("premu.all_cancelled", tx_hash=tx_hash.hex())
            return True
        except Exception as e:
            logger.error("premu.cancel_failed", error=str(e))
            return False

    def get_gas_balance(self) -> float:
        """Get ETH balance on Arbitrum for gas fees."""
        if not self._account:
            return 0.0
        balance = self.w3.eth.get_balance(self._account.address)
        return float(Web3.from_wei(balance, "ether"))
