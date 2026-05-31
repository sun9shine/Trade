"""
Premu.xyz Connector — Arbitrum Fast Markets (5-minute up/down outcomes).
Uses ERC-2612 permit standard for single-signature instant execution.
Implements full EIP-712 typed data signing for gasless token approvals.
"""

import time
from dataclasses import dataclass
from typing import Optional

import structlog
from web3 import Web3
from web3.middleware import geth_poa_middleware
from eth_account import Account
from eth_account.messages import encode_structured_data

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

# USDC token ABI for nonces() and DOMAIN_SEPARATOR
USDC_ABI = [
    {
        "inputs": [{"name": "owner", "type": "address"}],
        "name": "nonces",
        "outputs": [{"name": "", "type": "uint256"}],
        "stateMutability": "view",
        "type": "function",
    },
    {
        "inputs": [],
        "name": "name",
        "outputs": [{"name": "", "type": "string"}],
        "stateMutability": "view",
        "type": "function",
    },
    {
        "inputs": [],
        "name": "version",
        "outputs": [{"name": "", "type": "string"}],
        "stateMutability": "view",
        "type": "function",
    },
]

# Arbitrum USDC address
ARBITRUM_USDC_ADDRESS = "0xaf88d065e77c8cC2239327C5EDb3A432268e5831"


@dataclass
class PremuMarket:
    """Fast Market data from Premu."""
    market_id: bytes
    asset: str  # e.g., "BTC/USD", "ETH/USD"
    up_odds: float  # Probability for UP outcome (0-1)
    down_odds: float  # Probability for DOWN outcome (0-1)
    expires_at: int  # Unix timestamp
    status: int  # 0=open, 1=locked, 2=settled


class EIP712PermitSigner:
    """
    EIP-712 Typed Data signer for ERC-2612 Permit standard.
    Generates gasless approval signatures for USDC spending on Arbitrum.
    """

    def __init__(self, w3: Web3, token_address: str, chain_id: int = 42161):
        self.w3 = w3
        self.chain_id = chain_id
        self.token_address = Web3.to_checksum_address(token_address)
        self._token_contract = w3.eth.contract(
            address=self.token_address,
            abi=USDC_ABI,
        )
        self._token_name: Optional[str] = None
        self._token_version: Optional[str] = None

    def _get_token_name(self) -> str:
        """Fetch token name for EIP-712 domain (cached)."""
        if not self._token_name:
            try:
                self._token_name = self._token_contract.functions.name().call()
            except Exception:
                self._token_name = "USD Coin"
        return self._token_name

    def _get_token_version(self) -> str:
        """Fetch token version for EIP-712 domain (cached)."""
        if not self._token_version:
            try:
                self._token_version = self._token_contract.functions.version().call()
            except Exception:
                self._token_version = "2"
        return self._token_version

    def get_nonce(self, owner: str) -> int:
        """Get current permit nonce for an address."""
        return self._token_contract.functions.nonces(
            Web3.to_checksum_address(owner)
        ).call()

    def sign_permit(
        self,
        owner: str,
        spender: str,
        value: int,
        deadline: int,
        private_key: str,
    ) -> tuple[int, bytes, bytes]:
        """
        Sign an ERC-2612 permit using EIP-712 typed structured data.

        Returns: (v, r, s) signature components for on-chain verification.
        """
        owner = Web3.to_checksum_address(owner)
        spender = Web3.to_checksum_address(spender)
        nonce = self.get_nonce(owner)

        # EIP-712 typed data structure
        permit_data = {
            "types": {
                "EIP712Domain": [
                    {"name": "name", "type": "string"},
                    {"name": "version", "type": "string"},
                    {"name": "chainId", "type": "uint256"},
                    {"name": "verifyingContract", "type": "address"},
                ],
                "Permit": [
                    {"name": "owner", "type": "address"},
                    {"name": "spender", "type": "address"},
                    {"name": "value", "type": "uint256"},
                    {"name": "nonce", "type": "uint256"},
                    {"name": "deadline", "type": "uint256"},
                ],
            },
            "primaryType": "Permit",
            "domain": {
                "name": self._get_token_name(),
                "version": self._get_token_version(),
                "chainId": self.chain_id,
                "verifyingContract": self.token_address,
            },
            "message": {
                "owner": owner,
                "spender": spender,
                "value": value,
                "nonce": nonce,
                "deadline": deadline,
            },
        }

        # Encode and sign
        encoded = encode_structured_data(permit_data)
        signed = Account.sign_message(encoded, private_key=private_key)

        v = signed.v
        r = signed.r.to_bytes(32, byteorder="big")
        s = signed.s.to_bytes(32, byteorder="big")

        logger.debug(
            "eip712.permit_signed",
            owner=owner,
            spender=spender,
            value=value,
            nonce=nonce,
            deadline=deadline,
        )

        return v, r, s


class PremuConnector:
    """
    Interface to Premu.xyz on Arbitrum.
    Targets 5-minute Fast Markets with ERC-2612 permit execution.
    Full EIP-712 typed signing for gasless USDC approval.
    """

    def __init__(self):
        self.w3 = Web3(Web3.HTTPProvider(blockchain_settings.arbitrum_rpc_url))
        self.w3.middleware_onion.inject(geth_poa_middleware, layer=0)

        self._private_key = blockchain_settings.arbitrum_private_key
        self._account = None
        self._vault_contract = None
        self._permit_signer: Optional[EIP712PermitSigner] = None

    async def initialize(self):
        """Initialize Web3 connection, vault contract, and permit signer."""
        try:
            self._account = Account.from_key(self._private_key)
            vault_address = Web3.to_checksum_address(blockchain_settings.premu_vault_address)

            self._vault_contract = self.w3.eth.contract(
                address=vault_address,
                abi=PREMU_VAULT_ABI,
            )

            # Initialize EIP-712 permit signer for USDC
            self._permit_signer = EIP712PermitSigner(
                w3=self.w3,
                token_address=ARBITRUM_USDC_ADDRESS,
                chain_id=42161,
            )

            balance = self.w3.eth.get_balance(self._account.address)
            logger.info(
                "premu.initialized",
                chain="arbitrum",
                wallet=self._account.address,
                eth_balance=float(Web3.from_wei(balance, "ether")),
                permit_signer="EIP-712 ready",
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
        Single-signature instant execution using full EIP-712 typed data.
        """
        try:
            deadline = int(time.time()) + 300  # 5 minutes from now

            # Get vault address as the spender
            vault_address = self._vault_contract.address

            # Sign EIP-712 permit for USDC spending
            v, r, s = self._permit_signer.sign_permit(
                owner=self._account.address,
                spender=vault_address,
                value=amount_wei,
                deadline=deadline,
                private_key=self._private_key,
            )

            # Build transaction with real permit signature
            tx = self._vault_contract.functions.buyWithPermit(
                market_id, outcome, amount_wei, deadline, v, r, s
            ).build_transaction({
                "from": self._account.address,
                "nonce": self.w3.eth.get_transaction_count(self._account.address),
                "gas": 350000,
                "maxFeePerGas": self.w3.eth.gas_price * 2,
                "maxPriorityFeePerGas": Web3.to_wei(0.1, "gwei"),
                "chainId": 42161,  # Arbitrum One
                "type": 2,  # EIP-1559
            })

            signed_tx = self.w3.eth.account.sign_transaction(tx, self._private_key)
            tx_hash = self.w3.eth.send_raw_transaction(signed_tx.raw_transaction)

            logger.info(
                "premu.order_executed",
                market_id=market_id.hex(),
                outcome="UP" if outcome == 0 else "DOWN",
                amount_wei=amount_wei,
                tx_hash=tx_hash.hex(),
                permit="EIP-712 signed",
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
                "maxFeePerGas": self.w3.eth.gas_price * 2,
                "maxPriorityFeePerGas": Web3.to_wei(0.1, "gwei"),
                "chainId": 42161,
                "type": 2,
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
        try:
            balance = self.w3.eth.get_balance(self._account.address)
            return float(Web3.from_wei(balance, "ether"))
        except Exception:
            return 0.0
