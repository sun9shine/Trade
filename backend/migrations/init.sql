-- ============================================================================
-- Cross-Market Arbitrage Bot — Database Schema
-- PostgreSQL 15+ with UUID and timestamp defaults
-- ============================================================================

-- Enable UUID extension
CREATE EXTENSION IF NOT EXISTS "uuid-ossp";
CREATE EXTENSION IF NOT EXISTS "pgcrypto";

-- ─── ENCRYPTED CREDENTIALS VAULT ────────────────────────────────────────────

CREATE TABLE IF NOT EXISTS encrypted_credentials (
    id UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
    service_name VARCHAR(50) NOT NULL,
    key_name VARCHAR(100) NOT NULL,
    encrypted_value TEXT NOT NULL,
    created_at TIMESTAMPTZ DEFAULT NOW(),
    updated_at TIMESTAMPTZ DEFAULT NOW(),
    UNIQUE (service_name, key_name)
);

CREATE INDEX idx_credentials_service ON encrypted_credentials(service_name);

COMMENT ON TABLE encrypted_credentials IS 'AES-256-GCM encrypted API keys and wallet private keys';

-- ─── RPC ENDPOINTS ──────────────────────────────────────────────────────────

CREATE TABLE IF NOT EXISTS rpc_endpoints (
    id UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
    chain VARCHAR(30) NOT NULL,
    url VARCHAR(500) NOT NULL,
    priority INTEGER DEFAULT 0,
    is_active BOOLEAN DEFAULT TRUE,
    latency_ms FLOAT,
    updated_at TIMESTAMPTZ DEFAULT NOW()
);

CREATE INDEX idx_rpc_chain ON rpc_endpoints(chain, is_active);

COMMENT ON TABLE rpc_endpoints IS 'Custom RPC node endpoints per blockchain (Polygon, Arbitrum, Solana)';

-- ─── WEBHOOK ENDPOINTS ──────────────────────────────────────────────────────

CREATE TABLE IF NOT EXISTS webhook_endpoints (
    id UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
    name VARCHAR(100) NOT NULL,
    slug VARCHAR(100) UNIQUE NOT NULL,
    hmac_secret TEXT NOT NULL,
    source_type VARCHAR(50) NOT NULL,
    is_active BOOLEAN DEFAULT TRUE,
    last_received_at TIMESTAMPTZ,
    created_at TIMESTAMPTZ DEFAULT NOW()
);

CREATE INDEX idx_webhook_slug ON webhook_endpoints(slug);

COMMENT ON TABLE webhook_endpoints IS 'Registered webhook URLs for macroeconomic event ingestion';

-- ─── TRADE EXECUTIONS (Immutable Log) ───────────────────────────────────────

CREATE TABLE IF NOT EXISTS trade_executions (
    id UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
    platform VARCHAR(30) NOT NULL,
    market_id VARCHAR(200) NOT NULL,
    direction VARCHAR(10) NOT NULL,
    outcome VARCHAR(100),
    quantity FLOAT NOT NULL,
    price FLOAT NOT NULL,
    total_cost_usd FLOAT NOT NULL,
    gas_cost_usd FLOAT,
    tx_hash VARCHAR(200),
    status VARCHAR(20) DEFAULT 'pending',
    strategy VARCHAR(50) NOT NULL,
    signal_source VARCHAR(100),
    executed_at TIMESTAMPTZ DEFAULT NOW(),
    settled_at TIMESTAMPTZ,
    pnl_usd FLOAT
);

CREATE INDEX idx_trades_platform ON trade_executions(platform);
CREATE INDEX idx_trades_strategy ON trade_executions(strategy);
CREATE INDEX idx_trades_status ON trade_executions(status);
CREATE INDEX idx_trades_executed ON trade_executions(executed_at DESC);

COMMENT ON TABLE trade_executions IS 'Immutable record of every executed trade across all DEXs';

-- ─── OPEN POSITIONS ─────────────────────────────────────────────────────────

CREATE TABLE IF NOT EXISTS open_positions (
    id UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
    platform VARCHAR(30) NOT NULL,
    market_id VARCHAR(200) NOT NULL,
    market_title VARCHAR(500),
    outcome VARCHAR(100) NOT NULL,
    shares FLOAT NOT NULL,
    avg_entry_price FLOAT NOT NULL,
    current_price FLOAT,
    unrealized_pnl FLOAT,
    opened_at TIMESTAMPTZ DEFAULT NOW(),
    updated_at TIMESTAMPTZ DEFAULT NOW()
);

CREATE INDEX idx_positions_platform ON open_positions(platform);

COMMENT ON TABLE open_positions IS 'Current open positions across prediction markets';

-- ─── FOREX TICK BUFFER ──────────────────────────────────────────────────────

CREATE TABLE IF NOT EXISTS forex_ticks (
    id UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
    symbol VARCHAR(20) NOT NULL,
    bid FLOAT NOT NULL,
    ask FLOAT NOT NULL,
    spread FLOAT NOT NULL,
    source VARCHAR(20) NOT NULL,
    timestamp TIMESTAMPTZ NOT NULL
);

CREATE INDEX idx_ticks_symbol_time ON forex_ticks(symbol, timestamp DESC);

-- Auto-cleanup: keep only last 24 hours of ticks
-- (Use pg_cron or application-level cleanup)

COMMENT ON TABLE forex_ticks IS 'Rolling buffer of recent forex tick data for anomaly detection';

-- ─── MACRO EVENTS ───────────────────────────────────────────────────────────

CREATE TABLE IF NOT EXISTS macro_events (
    id UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
    event_type VARCHAR(100) NOT NULL,
    country VARCHAR(10) NOT NULL,
    headline VARCHAR(500) NOT NULL,
    actual_value VARCHAR(50),
    forecast_value VARCHAR(50),
    previous_value VARCHAR(50),
    impact_level VARCHAR(10) NOT NULL,
    source VARCHAR(50) NOT NULL,
    raw_payload TEXT,
    received_at TIMESTAMPTZ DEFAULT NOW(),
    processed BOOLEAN DEFAULT FALSE
);

CREATE INDEX idx_events_type ON macro_events(event_type);
CREATE INDEX idx_events_received ON macro_events(received_at DESC);

COMMENT ON TABLE macro_events IS 'Ingested macroeconomic events from webhook feeds';

-- ─── METRICS SNAPSHOTS ──────────────────────────────────────────────────────

CREATE TABLE IF NOT EXISTS metrics_snapshots (
    id UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
    total_pnl_usd FLOAT DEFAULT 0.0,
    open_position_count INTEGER DEFAULT 0,
    total_trades_today INTEGER DEFAULT 0,
    polygon_gas_balance FLOAT,
    arbitrum_gas_balance FLOAT,
    solana_gas_balance FLOAT,
    avg_latency_ms FLOAT,
    kill_switch_active BOOLEAN DEFAULT FALSE,
    recorded_at TIMESTAMPTZ DEFAULT NOW()
);

CREATE INDEX idx_metrics_time ON metrics_snapshots(recorded_at DESC);

COMMENT ON TABLE metrics_snapshots IS 'Periodic system health and performance snapshots';

-- ─── AUDIT LOG ──────────────────────────────────────────────────────────────

CREATE TABLE IF NOT EXISTS audit_log (
    id UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
    actor VARCHAR(50) DEFAULT 'system',
    action VARCHAR(100) NOT NULL,
    resource_type VARCHAR(50),
    resource_id VARCHAR(200),
    details JSONB,
    ip_address VARCHAR(45),
    created_at TIMESTAMPTZ DEFAULT NOW()
);

CREATE INDEX idx_audit_action ON audit_log(action);
CREATE INDEX idx_audit_time ON audit_log(created_at DESC);

COMMENT ON TABLE audit_log IS 'Security audit trail for all administrative actions';
