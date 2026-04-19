"""Unit tests for digikey.blocklist (Redis-backed jti blocklist)."""

from __future__ import annotations

import pytest

fakeredis = pytest.importorskip("fakeredis")


@pytest.fixture()
def fake_redis(monkeypatch):
    """Patch digikey.blocklist to use fakeredis and set URL."""
    from digikey import blocklist

    # Reset any memoized real client
    blocklist.reset_client_cache()
    monkeypatch.setenv("DIGIKEY_BLOCKLIST_REDIS_URL", "redis://fake")

    server = fakeredis.FakeServer()
    fake = fakeredis.FakeRedis(server=server, decode_responses=True)

    def _client():
        return fake

    # Swap the internal _get_client used by write/exists paths
    monkeypatch.setattr(blocklist, "_get_client", _client)
    yield fake, blocklist
    blocklist.reset_client_cache()


@pytest.mark.unit
def test_unconfigured_is_blocked_returns_false(monkeypatch):
    from digikey import blocklist

    monkeypatch.delenv("DIGIKEY_BLOCKLIST_REDIS_URL", raising=False)
    blocklist.reset_client_cache()
    assert blocklist.is_blocked("any-jti") is False
    assert blocklist.write_blocklist_bulk([("x", 60)]) == 0


@pytest.mark.unit
def test_write_and_check(fake_redis):
    _fake, blocklist = fake_redis
    written = blocklist.write_blocklist_bulk([("abc", 60), ("def", 120)])
    assert written == 2
    assert blocklist.is_blocked("abc") is True
    assert blocklist.is_blocked("def") is True
    assert blocklist.is_blocked("never-written") is False


@pytest.mark.unit
def test_write_skips_expired_entries(fake_redis):
    fake, blocklist = fake_redis
    written = blocklist.write_blocklist_bulk([("x", 0), ("y", -5), ("z", 30)])
    assert written == 1
    assert fake.exists("jti:z")
    assert not fake.exists("jti:x")
    assert not fake.exists("jti:y")


@pytest.mark.unit
def test_write_empty_is_noop(fake_redis):
    _fake, blocklist = fake_redis
    assert blocklist.write_blocklist_bulk([]) == 0


@pytest.mark.unit
def test_ttl_is_honored(fake_redis):
    fake, blocklist = fake_redis
    blocklist.write_blocklist_bulk([("abc", 99)])
    ttl = fake.ttl("jti:abc")
    assert 90 <= ttl <= 99


@pytest.mark.unit
def test_redis_error_raises_blocklist_unavailable(monkeypatch):
    from digikey import blocklist

    monkeypatch.setenv("DIGIKEY_BLOCKLIST_REDIS_URL", "redis://fake")
    blocklist.reset_client_cache()

    import redis

    class BrokenClient:
        def exists(self, *_a, **_k):
            raise redis.RedisError("boom")

        def pipeline(self, *_a, **_k):
            raise redis.RedisError("boom")

    monkeypatch.setattr(blocklist, "_get_client", lambda: BrokenClient())

    with pytest.raises(blocklist.BlocklistUnavailable):
        blocklist.is_blocked("x")
