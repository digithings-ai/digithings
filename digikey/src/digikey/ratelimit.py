"""In-process token-bucket rate limiter for DigiKey auth-sensitive routes.

Applied selectively (via FastAPI dependency) to the key-issuance and
JWT-mint endpoints. Exempt routes — ``/health``, ``/.well-known/jwks.json``,
and any future ``/healthz``, ``/metrics``, ``/v1/status`` — do not carry this
dependency and therefore incur zero overhead.

Design
------
* Per-client-IP token bucket. A bucket starts full (``burst`` tokens) and
  refills at ``per_min / 60`` tokens/second up to ``burst``.
* ``time.monotonic()`` drives the clock — immune to wall-clock jumps.
* An :class:`asyncio.Lock` guards bucket mutation so concurrent awaits on
  the same event loop stay consistent.
* Pure in-process. Cross-process sharing (multi-worker / multi-instance)
  is a documented follow-up; a Redis- or DigiBase-backed store is the
  intended upgrade path (see ``ARCHITECTURE.md`` §"Rate limiting").
* On breach: HTTP 429, JSON body ``{"detail": "rate_limited",
  "retry_after": N}``, plus a ``Retry-After: N`` header.

Configuration
-------------
* ``DIGIKEY_RL_PER_MIN`` — sustained requests per minute per IP (default 10).
* ``DIGIKEY_RL_BURST`` — burst capacity per IP (default 20).
"""

from __future__ import annotations

import asyncio
import logging
import math
import os
import time
from dataclasses import dataclass

from fastapi import FastAPI, Request, status
from fastapi.responses import JSONResponse

logger = logging.getLogger(__name__)

DEFAULT_PER_MIN = 10
DEFAULT_BURST = 20
# Cap the bucket table to avoid unbounded memory growth under IP churn / spoofed
# X-Forwarded-For values. When exceeded we drop the half that has been idle
# longest — an attacker who cycles IPs effectively resets their own state,
# which is fine; legitimate callers keep their bucket because recent activity
# refreshes ``updated_at``.
MAX_BUCKETS = 10_000


def _env_int(name: str, default: int) -> int:
    raw = (os.environ.get(name) or "").strip()
    if not raw:
        return default
    try:
        value = int(raw)
    except ValueError:
        logger.warning("%s=%r is not an int; falling back to %d", name, raw, default)
        return default
    return value if value > 0 else default


@dataclass
class _Bucket:
    tokens: float
    updated_at: float


class TokenBucketRateLimiter:
    """Per-IP token-bucket limiter."""

    def __init__(self, per_min: int | None = None, burst: int | None = None) -> None:
        self.per_min = (
            per_min if per_min is not None else _env_int("DIGIKEY_RL_PER_MIN", DEFAULT_PER_MIN)
        )
        self.burst = burst if burst is not None else _env_int("DIGIKEY_RL_BURST", DEFAULT_BURST)
        if self.per_min <= 0:
            self.per_min = DEFAULT_PER_MIN
        if self.burst <= 0:
            self.burst = DEFAULT_BURST
        self._refill_per_sec = self.per_min / 60.0
        self._buckets: dict[str, _Bucket] = {}
        self._lock = asyncio.Lock()

    @staticmethod
    def client_ip(request: Request) -> str:
        """Best-effort client IP extraction.

        ``X-Forwarded-For`` is trusted only because DigiKey sits behind a
        loopback-bound deployment; in production the reverse proxy should be
        the only thing setting this header.
        """
        xff = request.headers.get("x-forwarded-for")
        if xff:
            return xff.split(",", 1)[0].strip() or "unknown"
        real = request.headers.get("x-real-ip")
        if real:
            return real.strip() or "unknown"
        if request.client and request.client.host:
            return request.client.host
        return "unknown"

    def reset(self) -> None:
        """Drop all buckets (test helper)."""
        self._buckets.clear()

    def _evict_stale(self, now: float) -> None:
        """Drop the half of buckets that have been idle longest."""
        items = sorted(self._buckets.items(), key=lambda kv: kv[1].updated_at)
        drop = len(items) // 2 or 1
        for k, _ in items[:drop]:
            self._buckets.pop(k, None)

    async def check(self, key: str) -> tuple[bool, float]:
        """Consume one token for ``key``.

        Returns ``(allowed, retry_after_seconds)``. When allowed,
        ``retry_after_seconds`` is 0. When rejected, it is the integer-ceiling
        seconds until one token refills.
        """
        async with self._lock:
            now = time.monotonic()
            bucket = self._buckets.get(key)
            if bucket is None:
                if len(self._buckets) >= MAX_BUCKETS:
                    self._evict_stale(now)
                bucket = _Bucket(tokens=float(self.burst), updated_at=now)
                self._buckets[key] = bucket
            elapsed = max(0.0, now - bucket.updated_at)
            bucket.tokens = min(float(self.burst), bucket.tokens + elapsed * self._refill_per_sec)
            bucket.updated_at = now
            if bucket.tokens >= 1.0:
                bucket.tokens -= 1.0
                return True, 0.0
            needed = 1.0 - bucket.tokens
            retry_after = needed / self._refill_per_sec if self._refill_per_sec > 0 else 60.0
            return False, retry_after


_limiter: TokenBucketRateLimiter | None = None


def get_limiter() -> TokenBucketRateLimiter:
    """Return the process-wide limiter (lazy init, env-driven)."""
    global _limiter
    if _limiter is None:
        _limiter = TokenBucketRateLimiter()
    return _limiter


def reset_limiter_for_tests() -> None:
    """Drop the cached limiter so a test can re-read env vars."""
    global _limiter
    _limiter = None


class RateLimited(Exception):
    """Raised when a client exceeds the configured rate limit."""

    def __init__(self, retry_after: int) -> None:
        self.retry_after = retry_after
        super().__init__(f"rate_limited; retry_after={retry_after}s")


async def rate_limit_dependency(request: Request) -> None:
    """FastAPI dependency — raises :class:`RateLimited` on breach.

    Scoped via ``Depends(rate_limit_dependency)`` on protected routes only.
    """
    limiter = get_limiter()
    key = limiter.client_ip(request)
    allowed, retry_after = await limiter.check(key)
    if allowed:
        return
    retry_after_s = max(1, int(math.ceil(retry_after)))
    raise RateLimited(retry_after_s)


async def _rate_limited_handler(_request: Request, exc: Exception) -> JSONResponse:
    assert isinstance(exc, RateLimited)
    return JSONResponse(
        status_code=status.HTTP_429_TOO_MANY_REQUESTS,
        content={"detail": "rate_limited", "retry_after": exc.retry_after},
        headers={"Retry-After": str(exc.retry_after)},
    )


def register_rate_limit_handler(app: FastAPI) -> None:
    """Register the 429 JSON response handler on the FastAPI app."""
    app.add_exception_handler(RateLimited, _rate_limited_handler)
