"""Cross-cutting middleware: request IDs, simple per-IP rate limit.

We keep this in-house rather than pull in slowapi for the basic limiter
because the proxy hot path benefits from one less allocation. slowapi is
still in requirements.txt so callers can use it for /api/* routes if they
want richer policies.
"""

from __future__ import annotations

import time
import uuid
from collections import defaultdict, deque
from typing import Callable

from starlette.middleware.base import BaseHTTPMiddleware
from starlette.requests import Request
from starlette.responses import Response


class RequestIdMiddleware(BaseHTTPMiddleware):
    """Attach an X-Request-ID to every request/response.

    Honors an incoming header if present so an upstream load balancer's ID
    propagates end-to-end.
    """

    async def dispatch(self, request: Request, call_next: Callable):
        rid = request.headers.get("x-request-id") or uuid.uuid4().hex[:16]
        request.state.request_id = rid
        response: Response = await call_next(request)
        response.headers["X-Request-ID"] = rid
        return response


class RateLimitMiddleware(BaseHTTPMiddleware):
    """Per-IP fixed-window limiter for the proxy hot path only.

    We intentionally do NOT limit /api/* — that's the dashboard talking to
    its own backend over a private network in production. /v1/* is the public
    proxy surface.
    """

    def __init__(self, app, *, per_minute: int = 600):
        super().__init__(app)
        self._per_minute = per_minute
        self._buckets: dict[str, deque[float]] = defaultdict(deque)

    async def dispatch(self, request: Request, call_next: Callable):
        if not request.url.path.startswith("/v1/"):
            return await call_next(request)

        ip = (
            (request.headers.get("x-forwarded-for") or "").split(",")[0].strip()
            or (request.client.host if request.client else "unknown")
        )
        now = time.monotonic()
        window = self._buckets[ip]
        while window and now - window[0] > 60:
            window.popleft()
        if len(window) >= self._per_minute:
            return Response(
                content='{"error":{"type":"rate_limited","message":"Too many requests"}}',
                status_code=429,
                media_type="application/json",
                headers={"Retry-After": "30"},
            )
        window.append(now)
        return await call_next(request)
