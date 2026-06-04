"""Sliding-window rate limiter for FastAPI middleware. No external dependencies."""

from __future__ import annotations

import os
import time
from collections import deque
from threading import Lock

from digibase.errors import json_error_response

from fastapi import Request
from fastapi.responses import JSONResponse


class RateLimiter:
    """Per-IP sliding-window rate limiter.

    Designed for use in FastAPI middleware::

        limiter = RateLimiter()

        @app.middleware("http")
        async def rate_limit(request: Request, call_next):
            result = limiter.check(request, max_requests=10, window=60)
            if result is not None:
                return result
            return await call_next(request)
    """

    def __init__(self) -> None:
        # ip -> deque of request timestamps (monotonic float)
        self._windows: dict[str, deque[float]] = {}
        self._lock = Lock()

    def _get_ip(self, request: Request) -> str:
        direct = request.client.host if request.client else "unknown"
        trusted_raw = os.environ.get("DIGI_TRUSTED_PROXY_IPS", "")
        trusted = {t.strip() for t in trusted_raw.split(",") if t.strip()}
        if trusted and direct in trusted:
            xff = request.headers.get("X-Forwarded-For")
            if xff:
                return xff.split(",")[0].strip()
        return direct

    def check(
        self,
        request: Request,
        max_requests: int,
        window: int = 60,
        *,
        service: str = "digigraph",
    ) -> JSONResponse | None:
        """Return a 429 JSONResponse if the IP has exceeded its quota, else None.

        Rate limiting is disabled:
        - When DIGI_DISABLE_RATE_LIMIT=true (e.g. in tests/dev)
        - For requests from 'testclient' (FastAPI TestClient)
        """
        if os.environ.get("DIGI_DISABLE_RATE_LIMIT", "").lower() in ("1", "true", "yes"):
            return None
        ip = self._get_ip(request)
        # FastAPI TestClient sends requests from 'testclient' — never a real client.
        if ip == "testclient":
            return None
        now = time.monotonic()
        cutoff = now - window
        with self._lock:
            if ip not in self._windows:
                self._windows[ip] = deque()
            q = self._windows[ip]
            while q and q[0] < cutoff:
                q.popleft()
            if len(q) >= max_requests:
                return json_error_response(
                    status_code=429,
                    code="rate_limit_exceeded",
                    message=f"Rate limit exceeded: {max_requests} requests per {window}s.",
                    request=request,
                    service=service,
                    headers={"Retry-After": str(window)},
                )
            q.append(now)
        return None
