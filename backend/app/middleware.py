"""
Middleware — Rate limiting, request logging, and security headers.
"""

import time
from collections import defaultdict
from typing import Callable

import structlog
from fastapi import Request, Response, HTTPException
from fastapi.responses import JSONResponse
from starlette.middleware.base import BaseHTTPMiddleware

logger = structlog.get_logger(__name__)


# ─── RATE LIMITER ─────────────────────────────────────────────────────────────

class RateLimitStore:
    """In-memory sliding window rate limit store."""

    def __init__(self):
        self._requests: dict[str, list[float]] = defaultdict(list)

    def is_allowed(self, key: str, max_requests: int, window_seconds: int) -> bool:
        """Check if a request is allowed under the rate limit."""
        now = time.time()
        window_start = now - window_seconds

        # Clean old entries
        self._requests[key] = [
            ts for ts in self._requests[key] if ts > window_start
        ]

        if len(self._requests[key]) >= max_requests:
            return False

        self._requests[key].append(now)
        return True

    def get_remaining(self, key: str, max_requests: int, window_seconds: int) -> int:
        """Get remaining requests in current window."""
        now = time.time()
        window_start = now - window_seconds
        current = len([ts for ts in self._requests[key] if ts > window_start])
        return max(0, max_requests - current)


# Global rate limit store
rate_limit_store = RateLimitStore()

# Rate limit tiers
RATE_LIMITS = {
    # Path prefix → (max_requests, window_seconds)
    "/api/auth/login": (5, 60),          # 5 login attempts per minute
    "/api/credentials": (30, 60),         # 30 credential ops per minute
    "/api/kill-switch": (3, 60),          # 3 kill switch calls per minute
    "/api/webhooks/generate": (10, 60),   # 10 webhook generations per minute
    "/api/ingest/": (100, 60),            # 100 webhook ingestions per minute
    "/api/": (120, 60),                   # 120 general API calls per minute
}


class RateLimitMiddleware(BaseHTTPMiddleware):
    """
    Rate limiting middleware with tiered limits per endpoint.
    Uses client IP + path as the rate limit key.
    """

    async def dispatch(self, request: Request, call_next: Callable) -> Response:
        # Skip health check and docs
        path = request.url.path
        if path in ("/health", "/docs", "/openapi.json", "/redoc"):
            return await call_next(request)

        # Determine client IP
        client_ip = request.client.host if request.client else "unknown"
        forwarded = request.headers.get("X-Forwarded-For")
        if forwarded:
            client_ip = forwarded.split(",")[0].strip()

        # Find matching rate limit tier
        max_requests, window = self._get_limit(path)

        # Rate limit key: IP + path prefix
        key = f"{client_ip}:{self._get_prefix(path)}"

        if not rate_limit_store.is_allowed(key, max_requests, window):
            remaining = 0
            logger.warning(
                "rate_limit.exceeded",
                ip=client_ip,
                path=path,
                limit=max_requests,
            )
            return JSONResponse(
                status_code=429,
                content={"detail": "Rate limit exceeded. Try again later."},
                headers={
                    "X-RateLimit-Limit": str(max_requests),
                    "X-RateLimit-Remaining": "0",
                    "X-RateLimit-Window": str(window),
                    "Retry-After": str(window),
                },
            )

        # Process request
        response = await call_next(request)

        # Add rate limit headers
        remaining = rate_limit_store.get_remaining(key, max_requests, window)
        response.headers["X-RateLimit-Limit"] = str(max_requests)
        response.headers["X-RateLimit-Remaining"] = str(remaining)
        response.headers["X-RateLimit-Window"] = str(window)

        return response

    def _get_limit(self, path: str) -> tuple[int, int]:
        """Get rate limit for a path."""
        for prefix, limits in RATE_LIMITS.items():
            if path.startswith(prefix):
                return limits
        return (120, 60)  # Default

    def _get_prefix(self, path: str) -> str:
        """Get the matching prefix for grouping."""
        for prefix in RATE_LIMITS:
            if path.startswith(prefix):
                return prefix
        return "/api/"


# ─── REQUEST LOGGING MIDDLEWARE ───────────────────────────────────────────────

class RequestLoggingMiddleware(BaseHTTPMiddleware):
    """Log all requests with timing and status codes."""

    async def dispatch(self, request: Request, call_next: Callable) -> Response:
        start_time = time.time()
        path = request.url.path

        # Skip noisy endpoints
        if path in ("/health", "/ws"):
            return await call_next(request)

        response = await call_next(request)

        duration_ms = (time.time() - start_time) * 1000

        # Log based on status code
        log_data = {
            "method": request.method,
            "path": path,
            "status": response.status_code,
            "duration_ms": round(duration_ms, 1),
            "ip": request.client.host if request.client else "unknown",
        }

        if response.status_code >= 500:
            logger.error("http.request", **log_data)
        elif response.status_code >= 400:
            logger.warning("http.request", **log_data)
        else:
            logger.info("http.request", **log_data)

        return response


# ─── SECURITY HEADERS MIDDLEWARE ──────────────────────────────────────────────

class SecurityHeadersMiddleware(BaseHTTPMiddleware):
    """Add security headers to all responses."""

    async def dispatch(self, request: Request, call_next: Callable) -> Response:
        response = await call_next(request)

        response.headers["X-Content-Type-Options"] = "nosniff"
        response.headers["X-Frame-Options"] = "DENY"
        response.headers["X-XSS-Protection"] = "1; mode=block"
        response.headers["Strict-Transport-Security"] = "max-age=31536000; includeSubDomains"
        response.headers["Referrer-Policy"] = "strict-origin-when-cross-origin"
        response.headers["Permissions-Policy"] = "camera=(), microphone=(), geolocation=()"

        return response
