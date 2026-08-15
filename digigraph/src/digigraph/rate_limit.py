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

# RFC 6177 recommends providers assign end sites at least a /64, and commonly
# a /56 or /48 -- NOT a bare /64 as a ceiling. A single client can trivially
# cycle through billions of addresses within its own /64 (and, with a /56 or
# /48 allocation, through 256 or 65536 distinct /64s) to defeat exact-address
# rate limiting. Bucketing by /64 closes the cheapest, most common form of
# that rotation but does not eliminate it for clients whose ISP grants a
# larger allocation -- there is no bucket size that closes this for every
# real-world allocation without also merging unrelated /64 holders together.
# IPv4 space is far scarcer and NAT/CGNAT sharing already makes network-level
# bucketing too coarse (it would over-throttle unrelated clients behind the
# same NAT), so IPv4 addresses are bucketed individually.
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

    @staticmethod
    def _parse_trusted_proxies(
        trusted_raw: str,
    ) -> list[ipaddress.IPv4Network | ipaddress.IPv6Network]:
        """Parse DIGI_TRUSTED_PROXIES ("comma-separated hosts/CIDRs", per
        ARCHITECTURE.md) into IP networks. A bare host (no "/prefix") becomes
        a single-address /32 or /128 network. Entries that are neither a
        valid IP nor a valid CIDR are dropped rather than raising -- a typo
        in the env var should not crash the server, and treating it as "not
        trusted" (its natural effect once dropped) is the safe default.
        """
        networks: list[ipaddress.IPv4Network | ipaddress.IPv6Network] = []
        for entry in trusted_raw.split(","):
            entry = entry.strip()
            if not entry:
                continue
            try:
                networks.append(ipaddress.ip_network(entry, strict=False))
            except ValueError:
                continue
        return networks

    @staticmethod
    def _is_trusted(ip: str, networks: list[ipaddress.IPv4Network | ipaddress.IPv6Network]) -> bool:
        """Whether `ip` falls in any trusted network. Comparing parsed
        `ipaddress` objects (rather than raw strings) means e.g. a
        fully-expanded, upper-case IPv6 literal from a load balancer still
        matches a compressed, lower-case entry in DIGI_TRUSTED_PROXIES."""
        try:
            addr = ipaddress.ip_address(ip)
        except ValueError:
            return False
        return any(addr in net for net in networks)

    def _get_ip(self, request: Request) -> str:
        direct = request.client.host if request.client else "unknown"
        trusted_raw = os.environ.get("DIGI_TRUSTED_PROXIES", "")
        networks = self._parse_trusted_proxies(trusted_raw)
        if networks and self._is_trusted(direct, networks):
            # A header name may legally appear as several separate header
            # lines (RFC 9110 S5.3), each semantically equivalent to one
            # comma-joined line -- request.headers.get() returns only the
            # first such line, silently dropping any hop a later proxy
            # appended as its own line rather than appending to the existing
            # one. getlist() returns all of them.
            xff = ", ".join(request.headers.getlist("x-forwarded-for"))
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
                    if self._is_trusted(hop, networks):
                        continue
                    # A hop that isn't a parseable IP address carries no
                    # information -- it's neither one of our trusted proxies
                    # nor a usable client address (e.g. a client-supplied
                    # literal like "testclient", which check() would
                    # otherwise treat as the FastAPI TestClient sentinel and
                    # exempt from rate limiting entirely). Skip it and keep
                    # looking left rather than returning it as-is.
                    try:
                        ipaddress.ip_address(hop)
                    except ValueError:
                        continue
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
            mapped = addr.ipv4_mapped
            if mapped is not None:
                # An IPv4-mapped IPv6 address (::ffff:a.b.c.d) packs its
                # entire payload into the low 32 bits -- the top 64 bits
                # (the /64 network) are always zero, so masking to /64 would
                # collapse every mapped address (and IPv6 loopback ::1) onto
                # the identical bucket "::". Dual-stack servers (e.g. uvicorn
                # on host="::") report IPv4 peers in this form, so bucket by
                # the embedded IPv4 address instead of the /64 network.
                return str(mapped)
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
        # FastAPI TestClient's direct socket peer is always 'testclient' --
        # never a real client. Check the raw socket peer, not _get_ip()'s
        # return value: an attacker-controlled X-Forwarded-For hop could
        # otherwise spoof this literal string to disable rate limiting
        # entirely (see _get_ip's own hop validation for the other half of
        # that fix).
        if request.client and request.client.host == "testclient":
            return None
        ip = self._get_ip(request)
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
