"""DigiAuthMiddleware revocation check (ADR-0007)."""

from __future__ import annotations

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

fakeredis = pytest.importorskip("fakeredis")
jwt = pytest.importorskip("jwt")


def _issue_and_configure(monkeypatch):
    """Build a JWT signed with a fresh RSA key, wire env for local verify."""
    from cryptography.hazmat.primitives.asymmetric import rsa

    from digikey.crypto_keys import private_key_to_pem, public_key_to_pem
    from digikey.jwt_issue import issue_access_token

    key = rsa.generate_private_key(public_exponent=65537, key_size=2048)
    priv_pem = private_key_to_pem(key)
    pub_pem = public_key_to_pem(key.public_key())
    monkeypatch.setenv("DIGIKEY_ISSUER", "http://test-dk")
    monkeypatch.setenv("DIGIKEY_AUDIENCE", "digi-ecosystem")
    monkeypatch.setenv("DIGIKEY_PUBLIC_KEY_PEM", pub_pem)
    monkeypatch.delenv("DIGIKEY_JWKS_URL", raising=False)

    from cryptography.hazmat.primitives import serialization

    priv = serialization.load_pem_private_key(priv_pem.encode(), password=None)
    token, jti_val = issue_access_token(
        priv,
        kid="t1",
        sub="key:x",
        tenant_slug="acme",
        scopes=["digigraph:chat"],
        key_pub="dgk_prefix",
    )
    return token, jti_val


def _make_app() -> FastAPI:
    from digikey.integrations.service_middleware import attach_digi_auth_middleware

    app = FastAPI()

    def scopes_fn(method: str, path: str):
        if path == "/open":
            return None
        return ["digigraph:chat"]

    attach_digi_auth_middleware(app, service="test", path_scopes=scopes_fn)

    @app.get("/protected")
    def _p():
        return {"ok": True}

    @app.get("/open")
    def _o():
        return {"ok": True}

    return app


@pytest.mark.unit
def test_unblocked_token_passes(monkeypatch):
    token, _jti = _issue_and_configure(monkeypatch)
    monkeypatch.delenv("DIGIKEY_BLOCKLIST_REDIS_URL", raising=False)
    from digikey import blocklist

    blocklist.reset_client_cache()

    client = TestClient(_make_app())
    r = client.get("/protected", headers={"Authorization": f"Bearer {token}"})
    assert r.status_code == 200


@pytest.mark.unit
def test_blocked_token_returns_401(monkeypatch):
    token, jti_val = _issue_and_configure(monkeypatch)
    monkeypatch.setenv("DIGIKEY_BLOCKLIST_REDIS_URL", "redis://fake")
    from digikey import blocklist

    blocklist.reset_client_cache()
    fake = fakeredis.FakeRedis(decode_responses=True)
    monkeypatch.setattr(blocklist, "_get_client", lambda: fake)

    # Populate the blocklist with this jti
    fake.setex(f"jti:{jti_val}", 600, "1")

    client = TestClient(_make_app())
    r = client.get("/protected", headers={"Authorization": f"Bearer {token}"})
    assert r.status_code == 401
    assert r.json() == {"detail": "token_revoked"}


@pytest.mark.unit
def test_redis_unreachable_returns_503(monkeypatch):
    token, _jti = _issue_and_configure(monkeypatch)
    monkeypatch.setenv("DIGIKEY_BLOCKLIST_REDIS_URL", "redis://fake")
    from digikey import blocklist

    blocklist.reset_client_cache()

    def _get():
        # Simulate error inside is_blocked path
        class C:
            def exists(self, *_a, **_k):
                import redis

                raise redis.RedisError("down")

        return C()

    monkeypatch.setattr(blocklist, "_get_client", _get)

    client = TestClient(_make_app())
    r = client.get("/protected", headers={"Authorization": f"Bearer {token}"})
    assert r.status_code == 503
    assert r.json() == {"detail": "auth_backend_unavailable"}


@pytest.mark.unit
def test_unset_url_is_passthrough(monkeypatch):
    token, _jti = _issue_and_configure(monkeypatch)
    monkeypatch.delenv("DIGIKEY_BLOCKLIST_REDIS_URL", raising=False)
    from digikey import blocklist

    blocklist.reset_client_cache()

    client = TestClient(_make_app())
    r = client.get("/protected", headers={"Authorization": f"Bearer {token}"})
    assert r.status_code == 200
