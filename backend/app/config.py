"""
Centralized configuration module — all values sourced from environment variables.
"""

from pydantic_settings import BaseSettings
from pydantic import Field
from typing import Optional


class AppSettings(BaseSettings):
    """Application-level settings."""
    app_env: str = Field(default="development")
    app_secret_key: str = Field(default="change-me")
    jwt_secret: str = Field(default="change-me")
    encryption_master_key: str = Field(default="change-me")

    class Config:
        env_file = ".env"
        extra = "ignore"


class DatabaseSettings(BaseSettings):
    """Database connection settings."""
    database_url: str = Field(default="postgresql+asyncpg://localhost:5432/arbitrage_bot")
    redis_url: str = Field(default="redis://localhost:6379/0")

    class Config:
        env_file = ".env"
        extra = "ignore"


class ForexSettings(BaseSettings):
    """Forex broker connection settings."""
    mt5_login: Optional[str] = None
    mt5_password: Optional[str] = None
    mt5_server: Optional[str] = None
    oanda_api_key: Optional[str] = None
    oanda_account_id: Optional[str] = None
    oanda_environment: str = Field(default="practice")

    class Config:
        env_file = ".env"
        extra = "ignore"


class BlockchainSettings(BaseSettings):
    """Blockchain RPC and wallet settings."""
    # Polygon / Polymarket
    polygon_rpc_url: str = Field(default="https://polygon-rpc.com")
    polygon_private_key: Optional[str] = None
    polymarket_api_key: Optional[str] = None
    polymarket_api_secret: Optional[str] = None
    polymarket_passphrase: Optional[str] = None

    # Arbitrum / Premu
    arbitrum_rpc_url: str = Field(default="https://arb1.arbitrum.io/rpc")
    arbitrum_private_key: Optional[str] = None
    premu_vault_address: Optional[str] = None

    # Solana / Monaco
    solana_rpc_url: str = Field(default="https://api.mainnet-beta.solana.com")
    solana_private_key: Optional[str] = None

    class Config:
        env_file = ".env"
        extra = "ignore"


class RiskSettings(BaseSettings):
    """Risk management parameters."""
    max_position_size_usd: float = Field(default=1000.0)
    latency_arb_min_gap_pct: float = Field(default=1.5)
    neg_risk_threshold: float = Field(default=0.96)
    kill_switch_enabled: bool = Field(default=False)

    class Config:
        env_file = ".env"
        extra = "ignore"


# Singleton instances
app_settings = AppSettings()
db_settings = DatabaseSettings()
forex_settings = ForexSettings()
blockchain_settings = BlockchainSettings()
risk_settings = RiskSettings()
