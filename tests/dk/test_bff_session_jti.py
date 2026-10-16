"""BFF-session jti persistence + revocation parity (ADR-0007 / #3917).

Regression coverage for the defect where ``grant_type=bff_session`` minted a
``jti`` but never wrote a ``JtiIssuedRow``, so BFF JWTs could not be revoked or
rehydrated into the Redis blocklist.

These tests are written red-first: before the fix, no ``JtiIssuedRow`` exists
for a BFF jti and there is no subject-scoped revoke route.
"""

from __future__ import annotations

import time

import pytest
from fastapi.testclient import TestClient

fakeredis = pytest.importorskip("fakeredis")
jwt = pytest.importorskip("jwt")

pytestmark = pytest.mark.unit

BFF_TOKEN = "test-bff-token-for-jti-parity"
ADMIN_TOKEN = "admin-secret-for-jti-parity"


@pytest.fixture()
def client(monkeypatch, tmp_path):
    db_path = tmp_path / "dk.db"
    monkeypatch.setenv("DIGIKEY_DATABASE_URL", f"sqlite:///{db_path}")
    monkeypatch.setenv("DIGIKEY_ALLOW_EPHEMERAL_KEY", "1")
    monkeypatch.setenv("DIGIKEY_ADMIN_TOKEN", ADMIN_TOKEN)
    monkeypatch.setenv("DIGIKEY_BFF_TOKEN", BFF_TOKEN)
    monkeypatch.setenv("DIGIKEY_BLOCKLIST_REDIS_URL", "redis://fake")
    monkeypatch.delenv("DIGIKEY_LITELLM_PROXY_KEY", raising=False)

    from digikey import blocklist, db

    db._engine = None
    db._session_factory = None
    blocklist.reset_client_cache()

    fake = fakeredis.FakeRedis(decode_responses=True)
    monkeypatch.setattr(blocklist, "_get_client", lambda: fake)

    from digikey.server import app

    with TestClient(app) as c:
        c.fake_redis = fake  # type: ignore[attr-defined]
        yield c


def _bff_exchange(client: TestClient, subject: str = "user-1", tenant: str = "acme") -> dict:
    r = client.post(
        "/v1/oauth/token",
        headers={"Authorization": f"Bearer {BFF_TOKEN}"},
        json={"grant_type": "bff_session", "tenant_slug": tenant, "subject": subject},
    )
    assert r.status_code == 200, r.text
    return r.json()


def _jti(token: str) -> str:
    return jwt.decode(token, options={"verify_signature": False})["jti"]


def _load_row(jti_value: str):
    from digikey.db import session_factory
    from digikey.db_schema import JtiIssuedRow

    sf = session_factory()
    with sf() as session:
        return session.get(JtiIssuedRow, jti_value)


def test_bff_session_exchange_persists_jti_row(client: TestClient) -> None:
    ttl = 900
    body = _bff_exchange(client, subject="alice")
    jti_value = _jti(body["access_token"])

    row = _load_row(jti_value)
    assert row is not None, "bff_session jti must be persisted as JtiIssuedRow"
    assert row.api_key_id is None
    assert row.subject == "alice"
    assert abs(row.exp - (int(time.time()) + ttl)) <= 5


def test_bff_jti_insert_failure_refuses_token(client: TestClient, monkeypatch) -> None:
    def _boom(*_args, **_kwargs):
        raise RuntimeError("simulated jti_issued insert failure")

    monkeypatch.setattr("digikey.server.JtiIssuedRow", _boom)
    r = client.post(
        "/v1/oauth/token",
        headers={"Authorization": f"Bearer {BFF_TOKEN}"},
        json={"grant_type": "bff_session", "tenant_slug": "acme", "subject": "alice"},
    )
    assert r.status_code == 503
    assert "token issuance unavailable" in r.text


def test_bff_jti_is_revocable_and_blocklisted(client: TestClient) -> None:
    body = _bff_exchange(client, subject="bob")
    jti_value = _jti(body["access_token"])

    r = client.post(
        "/v1/admin/bff-sessions/revoke",
        headers={"Authorization": f"Bearer {ADMIN_TOKEN}"},
        json={"subject": "bob"},
    )
    assert r.status_code == 200, r.text
    assert r.json()["revoked"] is True
    assert r.json()["jtis_invalidated"] >= 1

    fake = client.fake_redis  # type: ignore[attr-defined]
    assert fake.exists(f"jti:{jti_value}")


def test_bff_revoke_then_rehydrate_after_redis_flush(client: TestClient) -> None:
    body = _bff_exchange(client, subject="carol")
    jti_value = _jti(body["access_token"])

    r = client.post(
        "/v1/admin/bff-sessions/revoke",
        headers={"Authorization": f"Bearer {ADMIN_TOKEN}"},
        json={"subject": "carol"},
    )
    assert r.status_code == 200, r.text

    # Simulate a Redis restart: blocklist is empty, only the durable row remains.
    fake = client.fake_redis  # type: ignore[attr-defined]
    fake.flushall()
    assert fake.exists(f"jti:{jti_value}") == 0

    from digikey.blocklist_rehydrate import rehydrate_blocklist_from_db
    from digikey.db import session_factory

    written = rehydrate_blocklist_from_db(session_factory)
    assert written >= 1
    assert fake.exists(f"jti:{jti_value}")


def test_bff_subject_revoke_requires_admin(client: TestClient) -> None:
    r = client.post("/v1/admin/bff-sessions/revoke", json={"subject": "dave"})
    assert r.status_code == 401


def test_bff_token_response_shape_unchanged(client: TestClient) -> None:
    body = _bff_exchange(client, subject="erin")
    assert set(body.keys()) == {"access_token", "token_type", "expires_in"}
    assert body["token_type"] == "Bearer"
    assert body["expires_in"] == 900
