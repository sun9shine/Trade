"""
Test configuration and shared fixtures.
"""

import asyncio
import os
import pytest
import pytest_asyncio

# Set test environment before importing app modules
os.environ["APP_ENV"] = "testing"
os.environ["APP_SECRET_KEY"] = "test-secret-key-12345"
os.environ["JWT_SECRET"] = "test-jwt-secret-67890"
os.environ["ENCRYPTION_MASTER_KEY"] = "dGVzdC1lbmNyeXB0aW9uLWtleS0zMi1ieXRlcw=="  # 32 bytes base64
os.environ["DATABASE_URL"] = "sqlite+aiosqlite:///./test.db"
os.environ["REDIS_URL"] = "redis://localhost:6379/1"
os.environ["POLYGON_RPC_URL"] = "https://polygon-rpc.com"
os.environ["ARBITRUM_RPC_URL"] = "https://arb1.arbitrum.io/rpc"
os.environ["SOLANA_RPC_URL"] = "https://api.mainnet-beta.solana.com"


@pytest.fixture(scope="session")
def event_loop():
    """Create an event loop for the test session."""
    loop = asyncio.new_event_loop()
    yield loop
    loop.close()


@pytest.fixture
def sample_tick_data():
    """Sample forex tick data for testing."""
    from app.connectors.forex_engine import TickData

    return TickData(
        symbol="EURUSD",
        bid=1.08500,
        ask=1.08520,
        spread=0.00020,
        source="oanda",
        timestamp_ms=1717200000000,
    )


@pytest.fixture
def sample_macro_event():
    """Sample macro economic event payload."""
    from app.engine.webhook_handler import MacroEventPayload

    return MacroEventPayload(
        event_type="interest_rate",
        country="US",
        headline="Fed raises rates by 25bps",
        actual_value="5.50%",
        forecast_value="5.25%",
        previous_value="5.25%",
        impact_level="high",
        source="reuters",
        timestamp_ms=1717200000000,
    )


@pytest.fixture
def sample_arb_signal():
    """Sample arbitrage signal for testing."""
    from app.engine.arbitrage_router import ArbSignal

    return ArbSignal(
        signal_type="latency_arb",
        source_symbol="EURUSD",
        platform="polymarket",
        market_id="0xtest_market_id",
        expected_edge_pct=2.5,
        direction="up",
        timestamp_ms=1717200000000,
    )
