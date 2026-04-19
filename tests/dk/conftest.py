"""Shared test fixtures for DigiKey tests."""

from __future__ import annotations

import pytest


@pytest.fixture
def fake_blocklist_redis(monkeypatch):
    """Wire digikey.blocklist onto an in-process fakeredis.

    Yields ``(fake_client, blocklist_module)`` so tests can both drive the
    backend directly (``fake.setex(...)``) and exercise the wrapper
    (``blocklist.is_blocked(...)``).
    """
    fakeredis = pytest.importorskip("fakeredis")
    from digikey import blocklist

    blocklist.reset_client_cache()
    monkeypatch.setenv("DIGIKEY_BLOCKLIST_REDIS_URL", "redis://fake")

    fake = fakeredis.FakeRedis(decode_responses=True)
    monkeypatch.setattr(blocklist, "_get_client", lambda: fake)
    yield fake, blocklist
    blocklist.reset_client_cache()
