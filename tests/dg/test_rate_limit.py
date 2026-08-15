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
        silently drop every hop appended as its own line, including the real
        client if it's the only thing on the dropped line."""
        monkeypatch.setenv("DIGI_TRUSTED_PROXIES", "10.0.0.1")
        limiter = RateLimiter()
        req = _make_request("10.0.0.1", xff_lines=["198.51.100.42", "10.0.0.1"])
        # Two header lines: "198.51.100.42" (the real client) and "10.0.0.1"
        # (our own trusted proxy, appended on its own line). Merged and read
        # right-to-left, the trusted trailing entry is skipped and the real
        # client is returned.
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
