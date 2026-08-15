"""Sliding-window rate limiter for FastAPI middleware. No external dependencies."""

from __future__ import annotations

import ipaddress
import logging
import os
import time
from collections import OrderedDict, deque
from threading import Lock

from digibase.errors import json_error_response
from fastapi import Request
from fastapi.responses import JSONResponse

logger = logging.getLogger(__name__)

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

# Number of check() calls between sweeps that drop fully-idle buckets from
# `_windows`. Each bucket's own deque is already bounded to `max_requests`
# entries by the popleft loop in check() -- the unbounded-growth risk is the
# *number* of distinct buckets (one per IP, or /64 allocation, ever seen), not
# any one bucket's size. A client hit once and never again leaves a
# permanent entry with no later check() call against that same bucket to
# clean it up. Sweeping on every call would make check() cost O(distinct
# buckets) instead of O(1); this interval trades sweep frequency for that
# per-call cost. The sweep itself is O(evicted + 1) rather than O(distinct
# buckets) -- see `_evict_idle_buckets` -- so this interval only bounds how
# often the (cheap) sweep runs, not the cost of any single run.
_SWEEP_INTERVAL = 1000


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
        # bucket -> deque of request timestamps (monotonic float). An
        # OrderedDict, not a plain dict: check() moves a bucket to the end
        # every time it accepts a request, so front-to-back order is exactly
        # ascending by "time of last accepted request" -- see
        # _evict_idle_buckets for why that ordering matters.
        self._windows: OrderedDict[str, deque[float]] = OrderedDict()
        self._lock = Lock()
        self._checks_since_sweep = 0
        # trusted_raw string -> parsed networks. _get_ip() re-reads
        # DIGI_TRUSTED_PROXIES and re-parses it on every request (so a
        # config change takes effect without a restart), but re-running the
        # warnings below on every single request for a misconfigured entry
        # would flood the log under normal traffic. Keyed by the exact raw
        # string so a genuine config change still gets parsed (and, if still
        # invalid, still warned about) -- see _parse_trusted_proxies.
        self._trusted_proxies_cache: dict[
            str, list[ipaddress.IPv4Network | ipaddress.IPv6Network]
        ] = {}

    def _parse_trusted_proxies(
        self,
        trusted_raw: str,
    ) -> list[ipaddress.IPv4Network | ipaddress.IPv6Network]:
        """Parse DIGI_TRUSTED_PROXIES ("comma-separated hosts/CIDRs", per
        ARCHITECTURE.md) into IP networks. A bare host (no "/prefix") becomes
        a single-address /32 or /128 network. Entries that are neither a
        valid IP nor a valid CIDR are dropped rather than raising -- a typo
        in the env var should not crash the server, and treating it as "not
        trusted" (its natural effect once dropped) is the safe default.

        Cached per instance by the exact `trusted_raw` string (see
        `_trusted_proxies_cache` in `__init__`): this runs on every request,
        and `DIGI_TRUSTED_PROXIES` is operator configuration, not attacker
        input, so it changes rarely if ever during a process's life --
        caching means a misconfigured entry logs its warning once per
        distinct value this instance has seen, not once per request.
        """
        cached = self._trusted_proxies_cache.get(trusted_raw)
        if cached is not None:
            return cached
        networks: list[ipaddress.IPv4Network | ipaddress.IPv6Network] = []
        for entry in trusted_raw.split(","):
            entry = entry.strip()
            if not entry:
                continue
            try:
                # strict=True first: a CIDR with non-zero host bits (e.g. a
                # typo'd "192.168.1.5/24" meant to be a single host) is
                # rejected rather than silently widened to the whole
                # "192.168.1.0/24" -- which would trust 254 addresses the
                # operator never intended.
                networks.append(ipaddress.ip_network(entry, strict=True))
            except ValueError:
                try:
                    widened = ipaddress.ip_network(entry, strict=False)
                except ValueError:
                    # Neither a valid IP/CIDR nor a widen-able one, e.g. a
                    # typo like "10.0.0.999" or a bare hostname -- log it so a
                    # misconfigured DIGI_TRUSTED_PROXIES entry shows up as a
                    # diagnosable warning instead of silently never trusting
                    # the proxy the operator intended.
                    logger.warning(
                        "DIGI_TRUSTED_PROXIES entry %r is neither a valid IP address "
                        "nor a valid CIDR network; ignoring it. Fix or remove this "
                        "entry -- as written it will never be trusted.",
                        entry,
                    )
                    continue
                logger.warning(
                    "DIGI_TRUSTED_PROXIES entry %r has host bits set for its prefix; "
                    "trusting the whole %s network. If this was meant to be a single "
                    "host, fix the prefix (e.g. /32 for IPv4, /128 for IPv6).",
                    entry,
                    widened,
                )
                networks.append(widened)
        self._trusted_proxies_cache[trusted_raw] = networks
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
        if isinstance(addr, ipaddress.IPv6Address) and addr.ipv4_mapped is not None:
            # A dual-stack listener reports an IPv4 proxy's peer address in
            # ::ffff:a.b.c.d form (see _bucket_key's mapped-address handling
            # above) -- compare by the embedded IPv4 address so a plain IPv4
            # entry in DIGI_TRUSTED_PROXIES still matches it.
            addr = addr.ipv4_mapped
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
                    # This is the entry our nearest trusted proxy appended
                    # for whatever it saw as its peer -- the boundary between
                    # what we trust and what the original, unvalidated
                    # caller supplied. If it isn't a parseable IP address
                    # (e.g. a client-supplied literal like "testclient",
                    # which check() would otherwise treat as the FastAPI
                    # TestClient sentinel and exempt from rate limiting
                    # entirely -- or an "ip:port" / "unknown" / hostname hop
                    # from a proxy that formats XFF non-standardly), we
                    # cannot trust anything at or past this position: the
                    # entries to its left are exactly the attacker-supplied
                    # portion the whole walk-from-the-right exists to
                    # distrust. Stop here and fall back to the direct peer
                    # rather than continuing left into that territory.
                    try:
                        ipaddress.ip_address(hop)
                    except ValueError:
                        break
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

            # Every check() call counts toward the next sweep, accepted or
            # rejected. A sustained flood of requests that are all rejected
            # (an attacker repeatedly hitting a bucket already over quota)
            # must not stall the sweep -- otherwise any other, genuinely
            # idle buckets already sitting in `_windows` would never get
            # reclaimed for as long as the reject flood continues.
            self._checks_since_sweep += 1
            due_for_sweep = self._checks_since_sweep >= _SWEEP_INTERVAL
            if due_for_sweep:
                self._checks_since_sweep = 0

            if len(q) >= max_requests:
                response = json_error_response(
                    status_code=429,
                    code="rate_limit_exceeded",
                    message=f"Rate limit exceeded: {max_requests} requests per {window}s.",
                    request=request,
                    service=service,
                    headers={"Retry-After": str(window)},
                )
            else:
                q.append(now)
                # Mark this bucket most-recently-touched. Only on the
                # accepted path (never on the 429-reject path above) -- see
                # _evict_idle_buckets for why that distinction is
                # load-bearing.
                self._windows.move_to_end(bucket)
                response = None

            if due_for_sweep:
                self._evict_idle_buckets(cutoff)
        return response

    def _evict_idle_buckets(self, cutoff: float) -> None:
        """Drop buckets that have gone untouched since before `cutoff` --
        i.e. no accepted request from that bucket since the current window
        opened. Must be called with `self._lock` held (see `check()`).

        `_windows` is an OrderedDict, and `check()` calls `move_to_end` on a
        bucket exactly when (and only when) it appends to that bucket's
        deque -- never on the 429-reject path. So front-to-back order is
        exactly ascending by "time of last accepted request," which is
        exactly the deque's own last entry, `q[-1]`: the front of the dict is
        always the least-recently-touched bucket. That lets this scan stop
        at the first still-active bucket instead of visiting the whole dict:
        `_windows` can grow to an attacker-controlled size (one bucket per
        IP or /64 allocation ever seen), and a full O(n) scan under
        `self._lock` would stall this process's single asyncio event loop
        for every concurrent request during a sustained flood. This scan is
        O(evicted + 1) instead.

        A 429-rejected touch deliberately does NOT call move_to_end: reject
        only happens when the bucket's deque already holds >= max_requests
        entries that all survived this call's own popleft-expiry loop
        (see check()), which means every entry still in it -- including
        `q[-1]` -- is already known to be >= this call's own cutoff. Bumping
        the bucket's order on a reject that doesn't change `q[-1]` would
        desynchronize order from content: a bucket rejected "now" but whose
        last real append was long ago would jump to the back of the order
        while its `q[-1]` stays old, breaking the front-to-back early-stop
        invariant above (a later, still-idle bucket could then hide behind
        it and never get scanned).

        A bucket whose very first request was already over quota
        (`max_requests <= 0`) is created but never appended-to or moved (see
        check()'s early-return-on-429 path), leaving a permanently empty
        deque. An empty deque is treated as unconditionally idle here --
        `q[-1]` is never evaluated on it -- so it gets reclaimed once the
        scan reaches it instead of raising IndexError.

        Assumes every `check()` call against this instance uses the same
        `window` -- true for every call site in this codebase, each of which
        owns a dedicated `RateLimiter()` instance (see server.py). A caller
        that mixes windows on a single shared instance should use a separate
        `RateLimiter` per window instead, the same way this codebase already
        does for its general vs. `require_tool_calls` budgets.
        """
        idle_keys = []
        for key, q in self._windows.items():
            if q and q[-1] >= cutoff:
                break
            idle_keys.append(key)
        for key in idle_keys:
            del self._windows[key]
