"""
Tests for resilience module — circuit breakers, retry logic, rate limiting.
"""

import asyncio
import time
import pytest
from unittest.mock import AsyncMock

from app.resilience import (
    CircuitBreaker,
    CircuitState,
    RPCFailover,
    retry_async,
)
from app.middleware import RateLimitStore


class TestCircuitBreaker:
    """Tests for CircuitBreaker pattern."""

    def test_initial_state_closed(self):
        cb = CircuitBreaker(name="test", failure_threshold=3)
        assert cb.state == CircuitState.CLOSED
        assert cb.can_execute() is True

    def test_opens_after_threshold_failures(self):
        cb = CircuitBreaker(name="test", failure_threshold=3)
        cb.record_failure()
        cb.record_failure()
        assert cb.state == CircuitState.CLOSED
        cb.record_failure()
        assert cb.state == CircuitState.OPEN
        assert cb.can_execute() is False

    def test_success_resets_failure_count(self):
        cb = CircuitBreaker(name="test", failure_threshold=3)
        cb.record_failure()
        cb.record_failure()
        cb.record_success()
        assert cb.failure_count == 0
        assert cb.state == CircuitState.CLOSED

    def test_half_open_after_recovery_timeout(self):
        cb = CircuitBreaker(name="test", failure_threshold=2, recovery_timeout=0.1)
        cb.record_failure()
        cb.record_failure()
        assert cb.state == CircuitState.OPEN

        time.sleep(0.15)
        assert cb.can_execute() is True
        assert cb.state == CircuitState.HALF_OPEN

    def test_half_open_closes_on_success(self):
        cb = CircuitBreaker(
            name="test", failure_threshold=2,
            recovery_timeout=0.01, half_open_max_calls=2,
        )
        cb.record_failure()
        cb.record_failure()
        time.sleep(0.02)
        cb.can_execute()  # Transition to half-open

        cb.record_success()
        cb.record_success()
        assert cb.state == CircuitState.CLOSED


class TestRPCFailover:
    """Tests for RPC endpoint failover."""

    def test_initial_url(self):
        failover = RPCFailover(
            endpoints=["http://rpc1.com", "http://rpc2.com"],
            name="test",
        )
        assert failover.current_url == "http://rpc1.com"

    def test_failover_on_repeated_failures(self):
        failover = RPCFailover(
            endpoints=["http://rpc1.com", "http://rpc2.com"],
            name="test",
        )
        failover.report_failure("http://rpc1.com")
        failover.report_failure("http://rpc1.com")
        failover.report_failure("http://rpc1.com")
        assert failover.current_url == "http://rpc2.com"

    def test_success_keeps_current(self):
        failover = RPCFailover(
            endpoints=["http://rpc1.com", "http://rpc2.com"],
            name="test",
        )
        failover.report_success("http://rpc1.com", 50.0)
        assert failover.current_url == "http://rpc1.com"

    def test_health_report(self):
        failover = RPCFailover(
            endpoints=["http://rpc1.com", "http://rpc2.com"],
            name="test",
        )
        failover.report_success("http://rpc1.com", 45.0)
        report = failover.get_health_report()
        assert report["active"] == "http://rpc1.com"
        assert "http://rpc1.com" in report["endpoints"]


class TestRetryAsync:
    """Tests for async retry decorator."""

    @pytest.mark.asyncio
    async def test_succeeds_on_first_try(self):
        call_count = 0

        @retry_async(max_retries=3, base_delay=0.01)
        async def succeed():
            nonlocal call_count
            call_count += 1
            return "success"

        result = await succeed()
        assert result == "success"
        assert call_count == 1

    @pytest.mark.asyncio
    async def test_retries_on_failure(self):
        call_count = 0

        @retry_async(max_retries=3, base_delay=0.01)
        async def fail_twice():
            nonlocal call_count
            call_count += 1
            if call_count < 3:
                raise ConnectionError("fail")
            return "recovered"

        result = await fail_twice()
        assert result == "recovered"
        assert call_count == 3

    @pytest.mark.asyncio
    async def test_exhausts_retries(self):
        @retry_async(max_retries=2, base_delay=0.01)
        async def always_fail():
            raise ValueError("permanent failure")

        with pytest.raises(ValueError, match="permanent failure"):
            await always_fail()


class TestRateLimitStore:
    """Tests for in-memory rate limit store."""

    def test_allows_within_limit(self):
        store = RateLimitStore()
        for _ in range(5):
            assert store.is_allowed("user1", max_requests=5, window_seconds=60) is True

    def test_blocks_over_limit(self):
        store = RateLimitStore()
        for _ in range(10):
            store.is_allowed("user2", max_requests=10, window_seconds=60)

        assert store.is_allowed("user2", max_requests=10, window_seconds=60) is False

    def test_different_keys_independent(self):
        store = RateLimitStore()
        for _ in range(5):
            store.is_allowed("key_a", max_requests=5, window_seconds=60)

        assert store.is_allowed("key_a", max_requests=5, window_seconds=60) is False
        assert store.is_allowed("key_b", max_requests=5, window_seconds=60) is True

    def test_remaining_count(self):
        store = RateLimitStore()
        store.is_allowed("user3", max_requests=10, window_seconds=60)
        store.is_allowed("user3", max_requests=10, window_seconds=60)

        remaining = store.get_remaining("user3", max_requests=10, window_seconds=60)
        assert remaining == 8
