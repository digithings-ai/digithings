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


def _make_request(client_host: str = "203.0.113.9", *, xff: str | None = None) -> Request:
    """A minimal real Starlette Request -- not FastAPI's TestClient -- so its
    client host isn't the 'testclient' sentinel that RateLimiter.check() exempts."""
    headers = []
    if xff is not None:
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
