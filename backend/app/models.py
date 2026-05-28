"""
SQLAlchemy models — PostgreSQL schema for the arbitrage bot.
"""

from datetime import datetime
from typing import Optional
from uuid import uuid4

from sqlalchemy import (
    Boolean,
    Column,
    DateTime,
    Enum,
    Float,
    Integer,
    String,
    Text,
    func,
)
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import DeclarativeBase


class Base(DeclarativeBase):
    pass


# ─── CREDENTIALS VAULT ───────────────────────────────────────────────────────

class EncryptedCredential(Base):
    """Stores encrypted API keys and private keys."""
    __tablename__ = "encrypted_credentials"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid4)
    service_name = Column(String(50), nullable=False, index=True)
    # e.g., "mt5", "oanda", "polymarket", "premu", "monaco"
    key_name = Column(String(100), nullable=False)
    # e.g., "api_key", "private_key", "passphrase"
    encrypted_value = Column(Text, nullable=False)  # AES-256-GCM encrypted
    created_at = Column(DateTime, server_default=func.now())
    updated_at = Column(DateTime, server_default=func.now(), onupdate=func.now())

    __table_args__ = (
        # Unique per service+key combination
        {"schema": None},
    )


# ─── RPC CONFIGURATION ───────────────────────────────────────────────────────

class RPCEndpoint(Base):
    """Custom RPC endpoint configurations per chain."""
    __tablename__ = "rpc_endpoints"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid4)
    chain = Column(String(30), nullable=False)  # polygon, arbitrum, solana
    url = Column(String(500), nullable=False)
    priority = Column(Integer, default=0)  # Higher = preferred
    is_active = Column(Boolean, default=True)
    latency_ms = Column(Float, nullable=True)  # Last measured latency
    updated_at = Column(DateTime, server_default=func.now(), onupdate=func.now())


# ─── WEBHOOK CONFIGURATION ───────────────────────────────────────────────────

class WebhookEndpoint(Base):
    """Registered webhook endpoints for macro-event ingestion."""
    __tablename__ = "webhook_endpoints"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid4)
    name = Column(String(100), nullable=False)
    slug = Column(String(100), unique=True, nullable=False)  # URL path segment
    hmac_secret = Column(Text, nullable=False)  # Encrypted
    source_type = Column(String(50), nullable=False)
    # e.g., "tradingview", "reuters", "bloomberg", "custom"
    is_active = Column(Boolean, default=True)
    last_received_at = Column(DateTime, nullable=True)
    created_at = Column(DateTime, server_default=func.now())


# ─── TRADE EXECUTION LOG ─────────────────────────────────────────────────────

class TradeExecution(Base):
    """Immutable log of every trade executed across all platforms."""
    __tablename__ = "trade_executions"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid4)
    platform = Column(String(30), nullable=False)
    # "polymarket", "premu", "monaco"
    market_id = Column(String(200), nullable=False)
    direction = Column(String(10), nullable=False)  # "buy" or "sell"
    outcome = Column(String(100), nullable=True)  # "yes", "no", or outcome label
    quantity = Column(Float, nullable=False)
    price = Column(Float, nullable=False)
    total_cost_usd = Column(Float, nullable=False)
    gas_cost_usd = Column(Float, nullable=True)
    tx_hash = Column(String(200), nullable=True)
    status = Column(String(20), default="pending")
    # "pending", "confirmed", "failed", "cancelled"
    strategy = Column(String(50), nullable=False)
    # "latency_arb", "neg_risk_arb", "manual"
    signal_source = Column(String(100), nullable=True)
    # What triggered this trade
    executed_at = Column(DateTime, server_default=func.now())
    settled_at = Column(DateTime, nullable=True)
    pnl_usd = Column(Float, nullable=True)


# ─── POSITION TRACKER ────────────────────────────────────────────────────────

class OpenPosition(Base):
    """Current open positions across all prediction markets."""
    __tablename__ = "open_positions"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid4)
    platform = Column(String(30), nullable=False)
    market_id = Column(String(200), nullable=False)
    market_title = Column(String(500), nullable=True)
    outcome = Column(String(100), nullable=False)
    shares = Column(Float, nullable=False)
    avg_entry_price = Column(Float, nullable=False)
    current_price = Column(Float, nullable=True)
    unrealized_pnl = Column(Float, nullable=True)
    opened_at = Column(DateTime, server_default=func.now())
    updated_at = Column(DateTime, server_default=func.now(), onupdate=func.now())


# ─── FOREX TICK BUFFER ────────────────────────────────────────────────────────

class ForexTick(Base):
    """High-frequency forex tick data (recent buffer only)."""
    __tablename__ = "forex_ticks"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid4)
    symbol = Column(String(20), nullable=False, index=True)
    bid = Column(Float, nullable=False)
    ask = Column(Float, nullable=False)
    spread = Column(Float, nullable=False)
    source = Column(String(20), nullable=False)  # "mt5", "oanda"
    timestamp = Column(DateTime, nullable=False, index=True)


# ─── MACRO EVENT LOG ─────────────────────────────────────────────────────────

class MacroEvent(Base):
    """Ingested macroeconomic events from webhooks."""
    __tablename__ = "macro_events"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid4)
    event_type = Column(String(100), nullable=False)
    # e.g., "interest_rate", "gdp", "inflation", "nfp"
    country = Column(String(10), nullable=False)
    headline = Column(String(500), nullable=False)
    actual_value = Column(String(50), nullable=True)
    forecast_value = Column(String(50), nullable=True)
    previous_value = Column(String(50), nullable=True)
    impact_level = Column(String(10), nullable=False)  # "high", "medium", "low"
    source = Column(String(50), nullable=False)
    raw_payload = Column(Text, nullable=True)
    received_at = Column(DateTime, server_default=func.now())
    processed = Column(Boolean, default=False)


# ─── SYSTEM METRICS SNAPSHOT ──────────────────────────────────────────────────

class MetricsSnapshot(Base):
    """Periodic system health and performance metrics."""
    __tablename__ = "metrics_snapshots"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid4)
    total_pnl_usd = Column(Float, default=0.0)
    open_position_count = Column(Integer, default=0)
    total_trades_today = Column(Integer, default=0)
    polygon_gas_balance = Column(Float, nullable=True)
    arbitrum_gas_balance = Column(Float, nullable=True)
    solana_gas_balance = Column(Float, nullable=True)
    avg_latency_ms = Column(Float, nullable=True)
    kill_switch_active = Column(Boolean, default=False)
    recorded_at = Column(DateTime, server_default=func.now())
