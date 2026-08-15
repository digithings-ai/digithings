"""Sliding-window rate limiter for FastAPI middleware. No external dependencies."""

from __future__ import annotations

import ipaddress
import os
import time
from collections import deque
from threading import Lock

from digibase.errors import json_error_response
from fastapi import Request
from fastapi.responses import JSONResponse

# IPv6 allocations to end users are conventionally a /64 or larger (RFC 6177) --
# a single client can trivially cycle through billions of addresses within its
# own /64 to defeat exact-address rate limiting. Bucket IPv6 addresses by /64 so
# rotation within one allocation still hits the same bucket. IPv4 space is far
# scarcer and NAT/CGNAT sharing already makes network-level bucketing too coarse
# (it would over-throttle unrelated clients behind the same NAT), so IPv4
# addresses are bucketed individually.
_IPV6_BUCKET_PREFIX = 64


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
        # bucket -> deque of request timestamps (monotonic float)
        self._windows: dict[str, deque[float]] = {}
        self._lock = Lock()

    def _get_ip(self, request: Request) -> str:
        direct = request.client.host if request.client else "unknown"
        trusted_raw = os.environ.get("DIGI_TRUSTED_PROXIES", "")
        trusted = {t.strip() for t in trusted_raw.split(",") if t.strip()}
        if trusted and direct in trusted:
            xff = request.headers.get("X-Forwarded-For")
            if xff:
                # X-Forwarded-For is appended left-to-right by each hop
                # ("client, proxy1, proxy2, ..."): the left-most entry is
                # supplied by whoever made the original request and is never
                # validated or stripped by later hops, so a client can simply
                # set it themselves to spoof any IP. Walk from the right,
                # skipping entries that are themselves one of our trusted
                # proxies (chained trusted hops) -- the first non-trusted
                # entry is the address our nearest trusted proxy actually
                # observed as its peer.
                hops = [h.strip() for h in xff.split(",") if h.strip()]
                for hop in reversed(hops):
                    if hop not in trusted:
                        return hop
        return direct

    @staticmethod
    def _bucket_key(ip: str) -> str:
        """Normalize an address to its rate-limit bucket.

        IPv6 addresses are bucketed by /64 (see module docstring) so a client
        rotating within its own allocation still lands in the same bucket.
        Anything that isn't a parseable IP address (IPv4, 'unknown',
        'testclient', or a malformed X-Forwarded-For hop) passes through
        unchanged -- it's either not routable or handled by its own
        special-case check in `check()`.
        """
        try:
            addr = ipaddress.ip_address(ip)
        except ValueError:
            return ip
        if addr.version == 6:
            network = ipaddress.ip_network(f"{ip}/{_IPV6_BUCKET_PREFIX}", strict=False)
            return str(network.network_address)
        return ip

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
        bucket = self._bucket_key(ip)
        now = time.monotonic()
        cutoff = now - window
        with self._lock:
            if bucket not in self._windows:
                self._windows[bucket] = deque()
            q = self._windows[bucket]
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
