"""
Resilience Module — Auto-reconnection, retry logic, circuit breakers.
Provides decorators and utilities for handling transient failures
across WebSocket connections, RPC nodes, and API calls.
"""

import asyncio
import time
import random
from dataclasses import dataclass, field
from enum import Enum
from functools import wraps
from typing import Callable, Optional, Any

import structlog

logger = structlog.get_logger(__name__)


class CircuitState(Enum):
    """Circuit breaker states."""
    CLOSED = "closed"       # Normal operation
    OPEN = "open"           # Failures exceeded threshold, rejecting calls
    HALF_OPEN = "half_open" # Testing if service recovered


@dataclass
class CircuitBreaker:
    """
    Circuit breaker pattern for external service connections.
    Opens after N consecutive failures, half-opens after cooldown.
    """
    name: str
    failure_threshold: int = 5
    recovery_timeout: float = 30.0  # seconds
    half_open_max_calls: int = 2

    state: CircuitState = CircuitState.CLOSED
    failure_count: int = 0
    success_count: int = 0
    last_failure_time: float = 0
    half_open_calls: int = 0

    def record_success(self):
        """Record a successful call."""
        if self.state == CircuitState.HALF_OPEN:
            self.half_open_calls += 1
            if self.half_open_calls >= self.half_open_max_calls:
                self.state = CircuitState.CLOSED
                self.failure_count = 0
                self.half_open_calls = 0
                logger.info("circuit_breaker.closed", name=self.name)
        else:
            self.failure_count = 0
            self.success_count += 1

    def record_failure(self):
        """Record a failed call."""
        self.failure_count += 1
        self.last_failure_time = time.time()

        if self.state == CircuitState.HALF_OPEN:
            self.state = CircuitState.OPEN
            self.half_open_calls = 0
            logger.warning("circuit_breaker.reopened", name=self.name)
        elif self.failure_count >= self.failure_threshold:
            self.state = CircuitState.OPEN
            logger.warning(
                "circuit_breaker.opened",
                name=self.name,
                failures=self.failure_count,
            )

    def can_execute(self) -> bool:
        """Check if a call is allowed through the circuit breaker."""
        if self.state == CircuitState.CLOSED:
            return True
        elif self.state == CircuitState.OPEN:
            # Check if cooldown has passed
            elapsed = time.time() - self.last_failure_time
            if elapsed >= self.recovery_timeout:
                self.state = CircuitState.HALF_OPEN
                self.half_open_calls = 0
                logger.info("circuit_breaker.half_open", name=self.name)
                return True
            return False
        else:  # HALF_OPEN
            return self.half_open_calls < self.half_open_max_calls


# Global circuit breakers for each service
_circuit_breakers: dict[str, CircuitBreaker] = {}


def get_circuit_breaker(name: str, **kwargs) -> CircuitBreaker:
    """Get or create a named circuit breaker."""
    if name not in _circuit_breakers:
        _circuit_breakers[name] = CircuitBreaker(name=name, **kwargs)
    return _circuit_breakers[name]


# ─── RETRY WITH EXPONENTIAL BACKOFF ──────────────────────────────────────────

def retry_async(
    max_retries: int = 3,
    base_delay: float = 1.0,
    max_delay: float = 60.0,
    exponential_base: float = 2.0,
    jitter: bool = True,
    retry_on: tuple = (Exception,),
    circuit_breaker_name: Optional[str] = None,
):
    """
    Decorator for async functions with exponential backoff retry.

    Args:
        max_retries: Maximum number of retry attempts
        base_delay: Initial delay in seconds
        max_delay: Maximum delay between retries
        exponential_base: Multiplier for exponential backoff
        jitter: Add random jitter to prevent thundering herd
        retry_on: Tuple of exception types to retry on
        circuit_breaker_name: Optional circuit breaker to use
    """
    def decorator(func: Callable):
        @wraps(func)
        async def wrapper(*args, **kwargs):
            cb = get_circuit_breaker(circuit_breaker_name) if circuit_breaker_name else None

            for attempt in range(max_retries + 1):
                # Check circuit breaker
                if cb and not cb.can_execute():
                    logger.warning(
                        "retry.circuit_open",
                        func=func.__name__,
                        circuit=circuit_breaker_name,
                    )
                    raise ConnectionError(f"Circuit breaker '{circuit_breaker_name}' is open")

                try:
                    result = await func(*args, **kwargs)
                    if cb:
                        cb.record_success()
                    return result

                except retry_on as e:
                    if cb:
                        cb.record_failure()

                    if attempt == max_retries:
                        logger.error(
                            "retry.exhausted",
                            func=func.__name__,
                            attempts=max_retries + 1,
                            error=str(e),
                        )
                        raise

                    # Calculate backoff delay
                    delay = min(base_delay * (exponential_base ** attempt), max_delay)
                    if jitter:
                        delay = delay * (0.5 + random.random())

                    logger.warning(
                        "retry.attempt",
                        func=func.__name__,
                        attempt=attempt + 1,
                        max_retries=max_retries,
                        delay=round(delay, 2),
                        error=str(e),
                    )
                    await asyncio.sleep(delay)

        return wrapper
    return decorator


# ─── AUTO-RECONNECTING WEBSOCKET ──────────────────────────────────────────────

class ReconnectingWebSocket:
    """
    WebSocket client with automatic reconnection.
    Handles connection drops, backoff, and health checks.
    """

    def __init__(
        self,
        url: str,
        name: str,
        on_message: Optional[Callable] = None,
        on_connect: Optional[Callable] = None,
        on_disconnect: Optional[Callable] = None,
        max_reconnect_delay: float = 60.0,
        ping_interval: float = 30.0,
        headers: Optional[dict] = None,
    ):
        self.url = url
        self.name = name
        self.on_message = on_message
        self.on_connect = on_connect
        self.on_disconnect = on_disconnect
        self.max_reconnect_delay = max_reconnect_delay
        self.ping_interval = ping_interval
        self.headers = headers or {}

        self._ws = None
        self._running = False
        self._reconnect_count = 0
        self._connected = False

    @property
    def is_connected(self) -> bool:
        return self._connected

    async def connect(self):
        """Start the reconnecting WebSocket loop."""
        import websockets

        self._running = True
        self._reconnect_count = 0

        while self._running:
            try:
                async with websockets.connect(
                    self.url,
                    extra_headers=self.headers,
                    ping_interval=self.ping_interval,
                    ping_timeout=10,
                    close_timeout=5,
                ) as ws:
                    self._ws = ws
                    self._connected = True
                    self._reconnect_count = 0

                    logger.info("ws.connected", name=self.name, url=self.url)
                    if self.on_connect:
                        await self.on_connect()

                    # Message receive loop
                    async for message in ws:
                        if not self._running:
                            break
                        if self.on_message:
                            await self.on_message(message)

            except asyncio.CancelledError:
                break
            except Exception as e:
                self._connected = False
                self._reconnect_count += 1

                if self.on_disconnect:
                    await self.on_disconnect()

                if not self._running:
                    break

                # Exponential backoff for reconnection
                delay = min(
                    2 ** self._reconnect_count + random.random(),
                    self.max_reconnect_delay,
                )
                logger.warning(
                    "ws.reconnecting",
                    name=self.name,
                    attempt=self._reconnect_count,
                    delay=round(delay, 1),
                    error=str(e),
                )
                await asyncio.sleep(delay)

        self._connected = False
        logger.info("ws.stopped", name=self.name)

    async def send(self, message: str):
        """Send a message if connected."""
        if self._ws and self._connected:
            await self._ws.send(message)

    async def close(self):
        """Gracefully close the connection."""
        self._running = False
        if self._ws:
            await self._ws.close()


# ─── RPC FAILOVER ─────────────────────────────────────────────────────────────

class RPCFailover:
    """
    Manages multiple RPC endpoints with automatic failover.
    Tracks latency and health of each endpoint.
    """

    def __init__(self, endpoints: list[str], name: str = "rpc"):
        self.name = name
        self._endpoints = endpoints
        self._current_index = 0
        self._health: dict[str, dict] = {
            url: {"healthy": True, "latency_ms": 0, "failures": 0}
            for url in endpoints
        }

    @property
    def current_url(self) -> str:
        """Get the current active endpoint."""
        if not self._endpoints:
            raise ValueError("No RPC endpoints configured")
        return self._endpoints[self._current_index]

    def report_success(self, url: str, latency_ms: float):
        """Report a successful RPC call."""
        if url in self._health:
            self._health[url]["healthy"] = True
            self._health[url]["latency_ms"] = latency_ms
            self._health[url]["failures"] = 0

    def report_failure(self, url: str):
        """Report a failed RPC call and potentially failover."""
        if url in self._health:
            self._health[url]["failures"] += 1
            if self._health[url]["failures"] >= 3:
                self._health[url]["healthy"] = False
                self._failover()

    def _failover(self):
        """Switch to the next healthy endpoint."""
        original = self._current_index
        for i in range(len(self._endpoints)):
            idx = (self._current_index + 1 + i) % len(self._endpoints)
            url = self._endpoints[idx]
            if self._health[url]["healthy"]:
                self._current_index = idx
                logger.warning(
                    "rpc.failover",
                    name=self.name,
                    from_url=self._endpoints[original],
                    to_url=self._endpoints[idx],
                )
                return
        # All unhealthy — reset and try the first one
        for health in self._health.values():
            health["healthy"] = True
            health["failures"] = 0
        self._current_index = 0
        logger.warning("rpc.all_unhealthy_reset", name=self.name)

    def get_health_report(self) -> dict:
        """Get health status of all endpoints."""
        return {
            "active": self.current_url,
            "endpoints": self._health,
        }
