"""DigiAuthContext.tenant_slug_verified provenance flag (#2303).

A JWT-derived tenant_slug is authoritative; a header-filled fallback is not.
Downstream services doing real tenant authorization must be able to tell them
apart via this flag rather than trusting tenant_slug alone.
"""

from __future__ import annotations

import pytest
from fastapi import FastAPI, Request
from fastapi.testclient import TestClient

jwt = pytest.importorskip("jwt")


def _configure(monkeypatch):
    from cryptography.hazmat.primitives import serialization
    from cryptography.hazmat.primitives.asymmetric import rsa
    from digikey.crypto_keys import private_key_to_pem, public_key_to_pem

    key = rsa.generate_private_key(public_exponent=65537, key_size=2048)
    priv_pem = private_key_to_pem(key)
    pub_pem = public_key_to_pem(key.public_key())
    monkeypatch.setenv("DIGIKEY_ISSUER", "http://test-dk")
    monkeypatch.setenv("DIGIKEY_AUDIENCE", "digi-ecosystem")
    monkeypatch.setenv("DIGIKEY_PUBLIC_KEY_PEM", pub_pem)
    monkeypatch.delenv("DIGIKEY_JWKS_URL", raising=False)
    monkeypatch.delenv("DIGIKEY_BLOCKLIST_REDIS_URL", raising=False)

    from digikey import blocklist

    blocklist.reset_client_cache()

    priv = serialization.load_pem_private_key(priv_pem.encode(), password=None)
    return priv


def _mint(priv, *, tenant_slug: str) -> str:
    from digikey.jwt_issue import issue_access_token

    token, _jti = issue_access_token(
        priv,
        kid="t1",
        sub="key:x",
        tenant_slug=tenant_slug,
        scopes=["digigraph:chat"],
        key_pub="dgk_prefix",
    )
    return token


def _make_app() -> FastAPI:
    from digikey.integrations.service_middleware import attach_digi_auth_middleware

    app = FastAPI()
    attach_digi_auth_middleware(app, service="test", path_scopes=lambda m, p: ["digigraph:chat"])

    @app.get("/protected")
    def _p(request: Request):
        ctx = request.state.digi_auth
        return {"tenant_slug": ctx.tenant_slug, "tenant_slug_verified": ctx.tenant_slug_verified}

    return app


@pytest.mark.unit
def test_jwt_tenant_slug_is_verified(monkeypatch):
    priv = _configure(monkeypatch)
    token = _mint(priv, tenant_slug="acme")

    client = TestClient(_make_app())
    r = client.get("/protected", headers={"Authorization": f"Bearer {token}"})
    assert r.status_code == 200
    assert r.json() == {"tenant_slug": "acme", "tenant_slug_verified": True}


@pytest.mark.unit
def test_header_fallback_tenant_slug_is_not_verified(monkeypatch):
    priv = _configure(monkeypatch)
    token = _mint(priv, tenant_slug="")

    client = TestClient(_make_app())
    r = client.get(
        "/protected",
        headers={"Authorization": f"Bearer {token}", "X-Digi-Tenant": "attacker-tenant"},
    )
    assert r.status_code == 200
    assert r.json() == {"tenant_slug": "attacker-tenant", "tenant_slug_verified": False}


@pytest.mark.unit
def test_no_tenant_slug_and_no_header_is_not_verified(monkeypatch):
    priv = _configure(monkeypatch)
    token = _mint(priv, tenant_slug="")

    client = TestClient(_make_app())
    r = client.get("/protected", headers={"Authorization": f"Bearer {token}"})
    assert r.status_code == 200
    assert r.json() == {"tenant_slug": "", "tenant_slug_verified": False}
