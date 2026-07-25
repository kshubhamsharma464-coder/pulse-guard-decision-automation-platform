"""Fixed-window rate limiting, keyed by client IP. In-memory only -- fine
for a single-process deployment or as a per-instance backstop in front of
an external gateway/WAF that does real distributed rate limiting;
documented as a known limitation (docs/auth.md) rather than silently
assumed to be sufficient at scale.

Disabled by default (Settings.rate_limit_enabled=False) specifically so
the existing test suite -- which fires dozens of requests back-to-back
against one TestClient/IP within the same fixed window -- is never
affected unless an operator opts in."""

import time
from collections import defaultdict
from typing import Dict, Tuple

from starlette.middleware.base import BaseHTTPMiddleware
from starlette.requests import Request
from starlette.responses import JSONResponse

from app.core.settings import get_settings


class RateLimitMiddleware(BaseHTTPMiddleware):
    def __init__(self, app):
        super().__init__(app)
        self._window_seconds = 60
        self._counts: Dict[str, Tuple[int, float]] = defaultdict(lambda: (0, 0.0))  # key -> (count, window_start)

    def _client_key(self, request: Request) -> str:
        client = request.client
        return f"ip:{client.host if client else 'unknown'}"

    async def dispatch(self, request: Request, call_next):
        settings = get_settings()
        if not settings.rate_limit_enabled:
            return await call_next(request)

        key = self._client_key(request)
        now = time.monotonic()
        count, window_start = self._counts[key]
        if now - window_start >= self._window_seconds:
            count, window_start = 0, now
        count += 1
        self._counts[key] = (count, window_start)

        if count > settings.rate_limit_requests_per_minute:
            retry_after = max(1, int(self._window_seconds - (now - window_start)))
            return JSONResponse(
                status_code=429,
                content={"detail": "Rate limit exceeded. Please slow down."},
                headers={"Retry-After": str(retry_after)},
            )
        return await call_next(request)
