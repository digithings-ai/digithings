"""Tests for digigraph.rate_limit.RateLimiter (X-Forwarded-For trust + IPv6 bucketing).

Follow-up fixes from the PR #2371 in-session review (#2375):
- `_get_ip` previously trusted the left-most X-Forwarded-For hop, which is
  client-supplied and spoofable (XFF is appended left-to-right by each hop,
  so the left-most entry is whatever the original caller wrote). It now
  walks the chain from the right, skipping trusted-proxy hops, and returns
  the first non-trusted entry.
- IPv6 addresses previously each got their own bucket, letting a client
  rotate through its own /64 allocation (RFC 6177) to dodge the limit.
  They're now bucketed by /64; IPv4 addresses are unaffected.
"""

from __future__ import annotations

import logging
import time
from collections import deque

import pytest
from digigraph.rate_limit import RateLimiter
from starlette.requests import Request


def _make_request(
    client_host: str = "203.0.113.9",
    *,
    xff: str | None = None,
    xff_lines: list[str] | None = None,
) -> Request:
    """A minimal real Starlette Request -- not FastAPI's TestClient -- so its
    client host isn't the 'testclient' sentinel that RateLimiter.check() exempts.

    `xff` sends a single X-Forwarded-For header line; `xff_lines` sends each
    string as its own separate header line (RFC 9110 S5.3 permits a header
    name to repeat, semantically equivalent to one comma-joined line) --
    mutually exclusive, `xff_lines` takes precedence if both are given.
    """
    headers = []
    if xff_lines is not None:
        headers.extend((b"x-forwarded-for", line.encode()) for line in xff_lines)
    elif xff is not None:
        headers.append((b"x-forwarded-for", xff.encode()))
    scope = {
        "type": "http",
        "method": "GET",
        "path": "/workflow",
        "headers": headers,
        "client": (client_host, 12345),
        "server": ("testserver", 80),
        "scheme": "http",
        "query_string": b"",
    }
    return Request(scope)


@pytest.fixture(autouse=True)
def _clean_env(monkeypatch):
    monkeypatch.delenv("DIGI_TRUSTED_PROXIES", raising=False)
    monkeypatch.delenv("DIGI_DISABLE_RATE_LIMIT", raising=False)


class TestGetIpTrust:
    def test_no_trusted_proxies_uses_direct_peer(self):
        """With DIGI_TRUSTED_PROXIES unset, XFF is never consulted -- direct
        peer is the only address that matters."""
        limiter = RateLimiter()
        req = _make_request("203.0.113.1", xff="198.51.100.1")
        assert limiter._get_ip(req) == "203.0.113.1"

    def test_untrusted_direct_peer_ignores_xff(self, monkeypatch):
        """A direct peer that isn't one of our trusted proxies can set
        whatever XFF it wants -- it's ignored."""
        monkeypatch.setenv("DIGI_TRUSTED_PROXIES", "10.0.0.1")
        limiter = RateLimiter()
        req = _make_request("203.0.113.1", xff="198.51.100.1")
        assert limiter._get_ip(req) == "203.0.113.1"

    def test_spoofed_leftmost_hop_is_not_trusted(self, monkeypatch):
        """A client can set X-Forwarded-For to anything before it reaches our
        trusted proxy: 'evil-spoofed-ip, real-client-ip' as observed by our
        proxy. The left-most entry must NOT be trusted blindly."""
        monkeypatch.setenv("DIGI_TRUSTED_PROXIES", "10.0.0.1")
        limiter = RateLimiter()
        req = _make_request("10.0.0.1", xff="203.0.113.250, 198.51.100.42")
        # Our proxy (10.0.0.1) saw 198.51.100.42 as its peer -- that's the
        # real client. 203.0.113.250 was attacker-supplied and must be ignored.
        assert limiter._get_ip(req) == "198.51.100.42"

    def test_chained_trusted_proxies_skipped_from_the_right(self, monkeypatch):
        """Multiple trusted hops in the chain (e.g. CDN -> internal LB) are
        all skipped; the first non-trusted entry from the right wins."""
        monkeypatch.setenv("DIGI_TRUSTED_PROXIES", "10.0.0.1,10.0.0.2")
        limiter = RateLimiter()
        req = _make_request("10.0.0.1", xff="198.51.100.42, 10.0.0.2")
        assert limiter._get_ip(req) == "198.51.100.42"

    def test_all_hops_trusted_falls_back_to_direct(self, monkeypatch):
        """If every XFF hop is itself trusted, there's no untrusted origin to
        report -- fall back to the direct peer rather than guessing."""
        monkeypatch.setenv("DIGI_TRUSTED_PROXIES", "10.0.0.1,10.0.0.2")
        limiter = RateLimiter()
        req = _make_request("10.0.0.1", xff="10.0.0.2")
        assert limiter._get_ip(req) == "10.0.0.1"

    def test_trusted_direct_peer_no_xff_uses_direct(self, monkeypatch):
        monkeypatch.setenv("DIGI_TRUSTED_PROXIES", "10.0.0.1")
        limiter = RateLimiter()
        req = _make_request("10.0.0.1")
        assert limiter._get_ip(req) == "10.0.0.1"


class TestGetIpTrustFollowUp:
    """Regression tests for the in-session review findings on PR #2377
    (issue #2375): multi-line X-Forwarded-For, unvalidated hops, CIDR trust
    ranges, and case/compression-insensitive IPv6 trust comparison."""

    def test_multiple_xff_header_lines_are_merged(self, monkeypatch):
        """X-Forwarded-For may legally appear as several separate header
        lines rather than one comma-joined line (RFC 9110 S5.3). Starlette's
        `Headers.get()` returns only the first such line -- using it would
        silently drop every hop on any later line.

        Line 1 is just the trusted proxy's own address (as it would be if a
        second trusted hop appended its own line); the real client only
        appears at the end of line 2. `.get()`-only code sees line 1 alone
        ("10.0.0.1", already trusted, no non-trusted hop left) and falls
        back to the direct peer -- also "10.0.0.1" here -- so this data
        genuinely distinguishes the two implementations, unlike a case where
        the real client happens to sit on the first line regardless."""
        monkeypatch.setenv("DIGI_TRUSTED_PROXIES", "10.0.0.1")
        limiter = RateLimiter()
        req = _make_request("10.0.0.1", xff_lines=["10.0.0.1", "198.51.100.42, 10.0.0.1"])
        assert limiter._get_ip(req) == "198.51.100.42"

    def test_spoofed_testclient_hop_is_not_returned(self, monkeypatch):
        """A hop that isn't a parseable IP address (e.g. an attacker-supplied
        literal 'testclient') must never be returned as the client IP --
        check() would treat that exact string as the FastAPI TestClient
        sentinel and exempt the caller from rate limiting entirely."""
        monkeypatch.setenv("DIGI_TRUSTED_PROXIES", "10.0.0.1")
        limiter = RateLimiter()
        req = _make_request("10.0.0.1", xff="testclient")
        # No valid non-trusted hop exists -- falls back to the direct peer,
        # never the spoofed literal.
        assert limiter._get_ip(req) != "testclient"
        assert limiter._get_ip(req) == "10.0.0.1"

    def test_spoofed_testclient_hop_does_not_disable_rate_limit(self, monkeypatch):
        """End-to-end: even if _get_ip() somehow returned 'testclient',
        check() must key its TestClient exemption off the real socket peer,
        not off _get_ip()'s (attacker-influenceable) return value."""
        monkeypatch.setenv("DIGI_TRUSTED_PROXIES", "10.0.0.1")
        limiter = RateLimiter()
        req = _make_request("10.0.0.1", xff="testclient")
        assert limiter.check(req, max_requests=1, window=60) is None
        result = limiter.check(req, max_requests=1, window=60)
        assert result is not None
        assert result.status_code == 429

    def test_trusted_proxies_accepts_cidr_ranges(self, monkeypatch):
        """DIGI_TRUSTED_PROXIES is documented (ARCHITECTURE.md) as accepting
        CIDR ranges, not just exact host addresses."""
        monkeypatch.setenv("DIGI_TRUSTED_PROXIES", "10.0.0.0/24")
        limiter = RateLimiter()
        req = _make_request("10.0.0.17", xff="198.51.100.42, 10.0.0.9")
        # Both 10.0.0.17 (direct peer) and 10.0.0.9 (chained hop) fall inside
        # the trusted /24 despite neither being listed as an exact address.
        assert limiter._get_ip(req) == "198.51.100.42"

    def test_trusted_hop_comparison_is_ip_normalized_not_string(self, monkeypatch):
        """A trusted IPv6 proxy written in compressed lower-case form in
        config must still be recognized when the header presents the same
        address fully expanded and upper-case -- raw string comparison would
        treat them as different hosts and return the proxy's own address
        instead of skipping past it to the real client."""
        monkeypatch.setenv("DIGI_TRUSTED_PROXIES", "2001:db8::1")
        limiter = RateLimiter()
        req = _make_request(
            "2001:db8::1",
            xff="2003:db8:4006:822::200e, 2001:0DB8:0000:0000:0000:0000:0000:0001",
        )
        assert limiter._get_ip(req) == "2003:db8:4006:822::200e"

    def test_invalid_trusted_proxies_entry_is_ignored_not_fatal(self, monkeypatch):
        """A malformed DIGI_TRUSTED_PROXIES entry must not crash the limiter --
        it's dropped, and the remaining valid entries still apply."""
        monkeypatch.setenv("DIGI_TRUSTED_PROXIES", "not-an-ip, 10.0.0.1")
        limiter = RateLimiter()
        req = _make_request("10.0.0.1", xff="198.51.100.42")
        assert limiter._get_ip(req) == "198.51.100.42"

    def test_invalid_trusted_proxies_entry_logs_a_warning(self, monkeypatch, caplog):
        """A fully-invalid entry (neither a valid IP nor a valid CIDR, even
        widened) is silently dropped -- but an operator needs a diagnostic
        signal that a typo in DIGI_TRUSTED_PROXIES means the proxy they
        intended to trust never actually got trusted (#2378 follow-up)."""
        monkeypatch.setenv("DIGI_TRUSTED_PROXIES", "not-an-ip, 10.0.0.1")
        limiter = RateLimiter()
        with caplog.at_level(logging.WARNING, logger="digigraph.rate_limit"):
            networks = limiter._parse_trusted_proxies("not-an-ip, 10.0.0.1")
        assert len(networks) == 1
        assert any(
            "not-an-ip" in record.getMessage() and "never be trusted" in record.getMessage()
            for record in caplog.records
        )

    def test_invalid_trusted_proxies_warning_is_not_repeated_per_request(self, monkeypatch, caplog):
        """`_get_ip` re-reads and re-parses DIGI_TRUSTED_PROXIES on every
        request, so an unbounded warning-per-parse would flood the log under
        normal traffic for a misconfigured entry -- a distinct issue from
        whether the entry is dropped at all (CodeRabbit follow-up on
        #2378/#2379). The warning must fire once per distinct raw value this
        limiter instance has seen, not once per request."""
        monkeypatch.setenv("DIGI_TRUSTED_PROXIES", "not-an-ip, 10.0.0.1")
        limiter = RateLimiter()
        req = _make_request("10.0.0.1", xff="198.51.100.42")
        with caplog.at_level(logging.WARNING, logger="digigraph.rate_limit"):
            for _ in range(5):
                assert limiter._get_ip(req) == "198.51.100.42"
        warnings = [r for r in caplog.records if "not-an-ip" in r.getMessage()]
        assert len(warnings) == 1

    def test_unparseable_boundary_hop_falls_back_to_direct_not_further_left(self, monkeypatch):
        """The first non-trusted hop is the boundary our trusted proxy itself
        appended -- everything to its left is exactly the unvalidated,
        attacker-supplied portion the walk-from-the-right exists to distrust.
        If that boundary hop isn't a parseable IP (a proxy reporting
        "ip:port", "unknown", or a hostname instead of a bare IP), the walk
        must stop and fall back to the direct peer -- not keep walking left
        into attacker-controlled entries, which would hand the attacker
        their own spoofed leftmost value as the trusted client IP."""
        monkeypatch.setenv("DIGI_TRUSTED_PROXIES", "10.0.0.1")
        limiter = RateLimiter()
        req = _make_request("10.0.0.1", xff="203.0.113.250, 198.51.100.42:53812")
        # "198.51.100.42:53812" (ip:port, as some proxies format it) is the
        # boundary hop and isn't a bare parseable IP -- must NOT fall through
        # to the attacker-supplied "203.0.113.250" on its left.
        assert limiter._get_ip(req) == "10.0.0.1"

    def test_trusted_proxy_matching_normalizes_ipv4_mapped_ipv6(self, monkeypatch):
        """A dual-stack listener reports an IPv4 proxy's peer address as
        ::ffff:a.b.c.d. A plain IPv4 entry in DIGI_TRUSTED_PROXIES must still
        recognize it as trusted -- otherwise every request through that
        proxy looks untrusted and XFF is never consulted."""
        monkeypatch.setenv("DIGI_TRUSTED_PROXIES", "10.0.0.1")
        limiter = RateLimiter()
        req = _make_request("::ffff:10.0.0.1", xff="198.51.100.42, 10.0.0.1")
        assert limiter._get_ip(req) == "198.51.100.42"


class TestBucketKey:
    def test_ipv4_bucketed_individually(self):
        assert RateLimiter._bucket_key("203.0.113.1") == "203.0.113.1"
        assert RateLimiter._bucket_key("203.0.113.2") == "203.0.113.2"

    def test_ipv6_addresses_in_same_64_share_a_bucket(self):
        a = RateLimiter._bucket_key("2001:db8:1234:5678::1")
        b = RateLimiter._bucket_key("2001:db8:1234:5678:ffff:ffff:ffff:ffff")
        assert a == b

    def test_ipv6_addresses_in_different_64_get_different_buckets(self):
        a = RateLimiter._bucket_key("2001:db8:1234:5678::1")
        b = RateLimiter._bucket_key("2001:db8:1234:5679::1")
        assert a != b

    def test_non_ip_values_pass_through_unchanged(self):
        assert RateLimiter._bucket_key("unknown") == "unknown"
        assert RateLimiter._bucket_key("testclient") == "testclient"

    def test_ipv4_mapped_ipv6_bucketed_by_embedded_ipv4_not_collapsed(self):
        """::ffff:a.b.c.d packs its whole payload into the low 32 bits, so a
        blanket /64 mask would zero all of it and collapse every mapped
        address (a dual-stack server's routine way of reporting IPv4 peers)
        onto one shared bucket. Each must instead bucket by its own embedded
        IPv4 address, matching plain-IPv4 bucketing for the same host."""
        a = RateLimiter._bucket_key("::ffff:203.0.113.5")
        b = RateLimiter._bucket_key("::ffff:198.51.100.9")
        assert a == "203.0.113.5"
        assert b == "198.51.100.9"
        assert a != b


class TestCheckIntegration:
    """End-to-end through `check()` -- confirms the bucket key, not just the
    raw IP, is what determines whether two requests share a rate-limit window."""

    def test_ipv6_rotation_within_64_still_hits_shared_limit(self):
        limiter = RateLimiter()
        req_a = _make_request("2001:db8:1234:5678::1")
        req_b = _make_request("2001:db8:1234:5678::2")
        assert limiter.check(req_a, max_requests=2, window=60) is None
        assert limiter.check(req_b, max_requests=2, window=60) is None
        # Third request from either address in the same /64 exceeds the shared budget.
        result = limiter.check(req_a, max_requests=2, window=60)
        assert result is not None
        assert result.status_code == 429

    def test_ipv4_addresses_do_not_share_a_bucket(self):
        limiter = RateLimiter()
        req_a = _make_request("203.0.113.1")
        req_b = _make_request("203.0.113.2")
        assert limiter.check(req_a, max_requests=1, window=60) is None
        # req_a is now over budget...
        assert limiter.check(req_a, max_requests=1, window=60) is not None
        # ...but req_b, a distinct IPv4 address, is untouched.
        assert limiter.check(req_b, max_requests=1, window=60) is None

    def test_spoofed_xff_cannot_bypass_limit_via_untrusted_peer(self):
        """Without DIGI_TRUSTED_PROXIES configured, X-Forwarded-For is inert --
        the limiter keys on the direct peer, so a client can't dodge its
        rate-limit bucket by lying about its origin."""
        limiter = RateLimiter()
        req = _make_request("203.0.113.1", xff="1.2.3.4")
        assert limiter.check(req, max_requests=1, window=60) is None
        # Same direct peer, different spoofed XFF -- still the same bucket.
        req2 = _make_request("203.0.113.1", xff="5.6.7.8")
        result = limiter.check(req2, max_requests=1, window=60)
        assert result is not None
        assert result.status_code == 429


class TestWindowEviction:
    """`_windows` grows one entry per distinct bucket ever seen and, before
    this fix, never shrank -- a client hit once and never again left a
    permanent dict entry with no later check() call to reclaim it (#2378).
    `check()` now sweeps idle buckets out of `_windows` every
    `_SWEEP_INTERVAL` calls, so a low interval makes the sweep observable in
    a unit test without needing 1000 real calls."""

    def test_idle_bucket_is_evicted_by_a_later_sweep(self, monkeypatch):
        monkeypatch.setattr("digigraph.rate_limit._SWEEP_INTERVAL", 1)
        limiter = RateLimiter()
        idle_req = _make_request("203.0.113.50")
        # This call creates the bucket. With the interval patched to 1, it
        # also triggers the very next sweep -- but this bucket's own entry is
        # `now`, so it survives sweeping itself.
        assert limiter.check(idle_req, max_requests=10, window=60) is None
        assert "203.0.113.50" in limiter._windows
        # Time doesn't actually advance in a unit test -- force this bucket's
        # only entry to look like it aged out of a 60s window.
        limiter._windows["203.0.113.50"][0] = time.monotonic() - 61
        # A second call, from a different bucket, triggers the next sweep and
        # must evict the now-idle bucket while keeping its own fresh one.
        other_req = _make_request("203.0.113.51")
        assert limiter.check(other_req, max_requests=10, window=60) is None
        assert "203.0.113.50" not in limiter._windows
        assert "203.0.113.51" in limiter._windows

    def test_active_bucket_is_not_evicted_by_a_sweep(self, monkeypatch):
        """A bucket with a recent request must survive a sweep even while a
        genuinely idle sibling bucket is reclaimed in that same sweep. (A
        single-bucket version of this test would pass even with eviction
        deleted entirely -- a lone bucket's own fresh append can never
        satisfy its own idle check -- so this uses two buckets to actually
        exercise the discrimination.)"""
        monkeypatch.setattr("digigraph.rate_limit._SWEEP_INTERVAL", 1)
        limiter = RateLimiter()
        idle_req = _make_request("203.0.113.56")
        active_req = _make_request("203.0.113.57")
        assert limiter.check(idle_req, max_requests=10, window=60) is None
        assert limiter.check(active_req, max_requests=10, window=60) is None
        limiter._windows["203.0.113.56"][0] = time.monotonic() - 61
        # A further touch on the active bucket triggers the next sweep; the
        # idle sibling must be evicted while the active bucket survives.
        assert limiter.check(active_req, max_requests=10, window=60) is None
        assert "203.0.113.56" not in limiter._windows
        assert "203.0.113.57" in limiter._windows

    def test_zero_max_requests_bucket_does_not_crash_a_later_sweep(self, monkeypatch):
        """A bucket rejected on its very first request (max_requests=0, an
        edge config that immediately 429s without ever appending -- see
        check()'s early-return-on-429 path) is left in `_windows` with a
        permanently empty deque. A later sweep must reclaim it, not raise
        IndexError on it (#2378 follow-up).

        _SWEEP_INTERVAL is patched to 2, not 1: the sweep counter now
        advances on rejected calls too (CodeRabbit follow-up on #2378/#2379),
        so at interval 1 the rejecting call would trigger its own sweep and
        evict the bucket immediately, collapsing the two steps this test
        means to check separately -- that the poisoned bucket survives
        (empty, not crashing anything) up to the point a sweep actually
        runs, and that the next sweep to reach it reclaims it cleanly."""
        monkeypatch.setattr("digigraph.rate_limit._SWEEP_INTERVAL", 2)
        limiter = RateLimiter()
        zero_req = _make_request("203.0.113.58")
        result = limiter.check(zero_req, max_requests=0, window=60)
        assert result is not None
        assert result.status_code == 429
        assert len(limiter._windows["203.0.113.58"]) == 0
        # A later call from a different bucket crosses the interval, triggers
        # the sweep, and must not raise -- and must reclaim the empty bucket.
        other_req = _make_request("203.0.113.59")
        assert limiter.check(other_req, max_requests=10, window=60) is None
        assert "203.0.113.58" not in limiter._windows
        assert "203.0.113.59" in limiter._windows

    def test_sweep_still_runs_during_a_sustained_reject_flood(self, monkeypatch):
        """The sweep counter must advance on rejected requests too, not just
        accepted ones (CodeRabbit follow-up on #2378/#2379). Before this fix,
        `_checks_since_sweep` only incremented on the accepted path, so an
        attacker sending nothing but already-over-quota requests to one
        bucket would silently stall the sweep for as long as the flood
        continued -- leaving any other, genuinely idle buckets already in
        `_windows` unreclaimed the whole time."""
        monkeypatch.setattr("digigraph.rate_limit._SWEEP_INTERVAL", 3)
        limiter = RateLimiter()
        # Both buckets are seeded directly (not via check()) so setup itself
        # consumes none of the patched interval -- it's crossed purely by
        # the reject loop below. "203.0.113.60" is idle; "203.0.113.61" is
        # already at quota, so every check() against it is rejected --
        # never appended or move_to_end'd.
        limiter._windows["203.0.113.60"] = deque([time.monotonic() - 61])
        limiter._windows["203.0.113.61"] = deque([time.monotonic()] * 10)
        flooded_req = _make_request("203.0.113.61")
        for _ in range(3):
            result = limiter.check(flooded_req, max_requests=10, window=60)
            assert result is not None
            assert result.status_code == 429
        # Three straight rejects crossed the (patched) sweep interval on
        # their own -- the idle sibling must have been reclaimed even though
        # not one of those three calls was accepted.
        assert "203.0.113.60" not in limiter._windows
        assert "203.0.113.61" in limiter._windows

    def test_sweep_does_not_run_before_the_interval_elapses(self, monkeypatch):
        """With the default (large) interval, an idle bucket is left alone
        until enough check() calls accumulate -- the sweep is periodic, not
        per-call."""
        monkeypatch.setattr("digigraph.rate_limit._SWEEP_INTERVAL", 5)
        limiter = RateLimiter()
        idle_req = _make_request("203.0.113.53")
        assert limiter.check(idle_req, max_requests=10, window=60) is None
        limiter._windows["203.0.113.53"][0] = time.monotonic() - 61
        other_req = _make_request("203.0.113.54")
        # Calls 2-4 (of 5) must not trigger a sweep yet.
        for _ in range(3):
            assert limiter.check(other_req, max_requests=10, window=60) is None
            assert "203.0.113.53" in limiter._windows
        # The 5th call crosses the interval and sweeps.
        assert limiter.check(other_req, max_requests=10, window=60) is None
        assert "203.0.113.53" not in limiter._windows
