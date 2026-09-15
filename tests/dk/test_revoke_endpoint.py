"""Integration test: POST /v1/admin/keys/{id}/revoke (ADR-0007)."""

from __future__ import annotations

import pytest
from fastapi.testclient import TestClient

fakeredis = pytest.importorskip("fakeredis")


@pytest.fixture()
def client(monkeypatch, tmp_path):
    # Fresh per-test SQLite db so schemas / rows don't leak across tests
    db_path = tmp_path / "dk.db"
    monkeypatch.setenv("DIGIKEY_DATABASE_URL", f"sqlite:///{db_path}")
    monkeypatch.setenv("DIGIKEY_ALLOW_EPHEMERAL_KEY", "1")
    monkeypatch.setenv("DIGIKEY_ADMIN_TOKEN", "admin-secret")
    monkeypatch.setenv("DIGIKEY_BLOCKLIST_REDIS_URL", "redis://fake")
    # Reset module-level singletons so env takes effect
    from digikey import blocklist, db

    db._engine = None
    db._session_factory = None
    blocklist.reset_client_cache()

    fake = fakeredis.FakeRedis(decode_responses=True)
    monkeypatch.setattr(blocklist, "_get_client", lambda: fake)

    # Build public JWKS/PEM so jwt_verify has a key (for subsequent middleware tests).
    # Via monkeypatch, never a bare os.environ[] write: load_or_create_signing_key()
    # mints a fresh keypair, so a direct write permanently replaces the session
    # keypair tests/conftest.py installed. Any later suite that authenticates with a
    # session-minted token (tests/contracts) then fails signature verification with a
    # 401 instead of reaching its own assertion (#4125).
    from digikey.crypto_keys import load_or_create_signing_key, public_key_to_pem

    priv, _kid = load_or_create_signing_key()
    monkeypatch.setenv("DIGIKEY_PUBLIC_KEY_PEM", public_key_to_pem(priv.public_key()))

    from digikey.server import app

    # Trigger startup (TestClient context manager runs startup handlers)
    with TestClient(app) as c:
        c.fake_redis = fake  # type: ignore[attr-defined]
        yield c


def _create_key(client: TestClient) -> tuple[str, str]:
    r = client.post(
        "/v1/admin/keys",
        json={"tenant_slug": "acme", "label": "test", "scopes": ["digigraph:chat"]},
        headers={"Authorization": "Bearer admin-secret"},
    )
    assert r.status_code == 200, r.text
    data = r.json()
    return data["id"], data["api_key"]


def _exchange(client: TestClient, api_key: str) -> str:
    r = client.post(
        "/v1/oauth/token",
        json={"grant_type": "api_key", "api_key": api_key},
    )
    assert r.status_code == 200, r.text
    return r.json()["access_token"]


@pytest.mark.unit
def test_revoke_requires_admin(client: TestClient):
    r = client.post("/v1/admin/keys/some-id/revoke")
    assert r.status_code == 401


@pytest.mark.unit
def test_revoke_missing_key_404(client: TestClient):
    r = client.post(
        "/v1/admin/keys/no-such/revoke",
        headers={"Authorization": "Bearer admin-secret"},
    )
    assert r.status_code == 404


@pytest.mark.unit
def test_revoke_writes_jtis_to_blocklist(client: TestClient):
    key_id, raw = _create_key(client)
    # Issue two tokens from this key
    tok1 = _exchange(client, raw)
    tok2 = _exchange(client, raw)
    assert tok1 and tok2

    r = client.post(
        f"/v1/admin/keys/{key_id}/revoke",
        headers={"Authorization": "Bearer admin-secret"},
    )
    assert r.status_code == 200, r.text
    body = r.json()
    assert body["revoked"] is True
    assert body["jtis_invalidated"] == 2

    # Both tokens' jtis should now be in the fake Redis
    fake = client.fake_redis  # type: ignore[attr-defined]

    import jwt as pyjwt

    for tok in (tok1, tok2):
        claims = pyjwt.decode(tok, options={"verify_signature": False})
        assert fake.exists(f"jti:{claims['jti']}")


@pytest.mark.unit
def test_revoke_blocks_future_exchanges(client: TestClient):
    key_id, raw = _create_key(client)
    _exchange(client, raw)

    client.post(
        f"/v1/admin/keys/{key_id}/revoke",
        headers={"Authorization": "Bearer admin-secret"},
    )
    r = client.post("/v1/oauth/token", json={"grant_type": "api_key", "api_key": raw})
    assert r.status_code == 401


@pytest.mark.unit
def test_revoke_is_idempotent(client: TestClient):
    key_id, raw = _create_key(client)
    _exchange(client, raw)
    first = client.post(
        f"/v1/admin/keys/{key_id}/revoke",
        headers={"Authorization": "Bearer admin-secret"},
    )
    assert first.status_code == 200
    second = client.post(
        f"/v1/admin/keys/{key_id}/revoke",
        headers={"Authorization": "Bearer admin-secret"},
    )
    assert second.status_code == 200
    # Second revoke is a no-op from a security standpoint — the jtis remain
    # in the blocklist; the count reflects live DB rows (safe to re-push).
    assert second.json()["revoked"] is True


@pytest.mark.unit
def test_module_does_not_replace_the_session_keypair() -> None:
    """A session-minted token still verifies after this module ran (#4125).

    Deliberately takes no fixture and sits last in the file, so it observes what the
    tests above left behind. ``client`` mints a fresh keypair and publishes its public
    half, so if that publish ever goes back to a bare ``os.environ[]`` write the
    session keypair from ``tests/conftest.py`` is gone and this verification fails —
    which is precisely the 401 ``tests/contracts`` hit when it ran after this module.
    """
    from digikey.jwt_verify import decode_token

    from tests.digi_test_jwt import mint_test_jwt

    claims = decode_token(mint_test_jwt())
    assert claims.sub == "pytest-sub"
