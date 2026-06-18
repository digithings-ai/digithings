"""REM-005/019: blocklist rehydrate from jti_issued on startup."""

from __future__ import annotations

import time

import pytest

from digikey.db import init_db
from digikey.db_schema import ApiKeyRow, JtiIssuedRow, utcnow


@pytest.mark.unit
def test_rehydrate_writes_revoked_key_jtis(fake_blocklist_redis, monkeypatch, tmp_path):
    _fake, blocklist = fake_blocklist_redis
    from digikey import db as dk_db
    from digikey.blocklist_rehydrate import rehydrate_blocklist_from_db

    db_path = tmp_path / "digikey.db"
    monkeypatch.setenv("DIGIKEY_DATABASE_URL", f"sqlite:///{db_path}")
    dk_db._engine = None
    dk_db._session_factory = None
    from digikey.db import session_factory

    init_db()

    now_ts = int(time.time())
    sf = session_factory()
    with sf() as session:
        key = ApiKeyRow(
            id="key-1",
            key_hash="x",
            key_prefix="pfx",
            tenant_slug="t",
            scopes=[],
            revoked_at=utcnow(),
        )
        session.add(key)
        session.add(
            JtiIssuedRow(jti="live-jti", api_key_id="key-1", exp=now_ts + 3600),
        )
        session.add(
            JtiIssuedRow(jti="expired-jti", api_key_id="key-1", exp=now_ts - 10),
        )
        session.commit()

    written = rehydrate_blocklist_from_db(session_factory)
    assert written == 1
    assert blocklist.is_blocked("live-jti") is True
    assert blocklist.is_blocked("expired-jti") is False


@pytest.mark.unit
def test_require_blocklist_unconfigured_raises(monkeypatch):
    from digikey import blocklist

    monkeypatch.setenv("DIGIKEY_REQUIRE_BLOCKLIST", "1")
    monkeypatch.delenv("DIGIKEY_BLOCKLIST_REDIS_URL", raising=False)
    blocklist.reset_client_cache()
    with pytest.raises(blocklist.BlocklistUnavailable):
        blocklist.assert_blocklist_ready()
