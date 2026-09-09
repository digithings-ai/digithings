"""Refuse blank / whitespace-only tenant_slug on HTTP issuance paths.

CLI already rejected ``--tenant ""`` / ``"   "`` (#2303 / #2478). Admin key issue and
``bff_session`` still accepted whitespace that ``.strip()`` turned into an empty JWT
claim, unlocking the unsigned ``X-Digi-Tenant`` header fallback for corpus/vault
authorization.
"""

from __future__ import annotations

import pytest
from fastapi.testclient import TestClient


@pytest.fixture()
def client(monkeypatch, tmp_path):
    db_path = tmp_path / "dk.db"
    monkeypatch.setenv("DIGIKEY_DATABASE_URL", f"sqlite:///{db_path}")
    monkeypatch.setenv("DIGIKEY_ALLOW_EPHEMERAL_KEY", "1")
    monkeypatch.setenv("DIGIKEY_ADMIN_TOKEN", "admin-secret")
    monkeypatch.setenv("DIGIKEY_BFF_TOKEN", "bff-secret")
    monkeypatch.delenv("DIGIKEY_ALLOW_DEV_GLOBAL", raising=False)

    from digikey import db

    db._engine = None
    db._session_factory = None

    from digikey.server import app

    with TestClient(app) as c:
        yield c


@pytest.mark.unit
@pytest.mark.parametrize("tenant", [" ", "\t", "\n", "  "])
def test_admin_issue_rejects_whitespace_tenant(client: TestClient, tenant: str) -> None:
    r = client.post(
        "/v1/admin/keys",
        json={"tenant_slug": tenant, "label": "blank", "scopes": ["digigraph:chat"]},
        headers={"Authorization": "Bearer admin-secret"},
    )
    assert r.status_code == 422


@pytest.mark.unit
def test_admin_issue_accepts_padded_tenant(client: TestClient) -> None:
    r = client.post(
        "/v1/admin/keys",
        json={"tenant_slug": " acme ", "label": "ok", "scopes": ["digigraph:chat"]},
        headers={"Authorization": "Bearer admin-secret"},
    )
    assert r.status_code == 200, r.text
    assert r.json()["api_key"].startswith("dgk_live_")


@pytest.mark.unit
@pytest.mark.parametrize("tenant", [" ", "\t", "  "])
def test_bff_session_rejects_whitespace_tenant(client: TestClient, tenant: str) -> None:
    r = client.post(
        "/v1/oauth/token",
        json={
            "grant_type": "bff_session",
            "tenant_slug": tenant,
            "subject": "user-1",
        },
        headers={"Authorization": "Bearer bff-secret"},
    )
    assert r.status_code == 400
    body = r.json()
    msg = (body.get("detail") or body.get("error", {}).get("message") or "").lower()
    assert "blank" in msg


@pytest.mark.unit
def test_bff_session_accepts_padded_tenant(client: TestClient) -> None:
    r = client.post(
        "/v1/oauth/token",
        json={
            "grant_type": "bff_session",
            "tenant_slug": " digithings ",
            "subject": "user-1",
        },
        headers={"Authorization": "Bearer bff-secret"},
    )
    assert r.status_code == 200, r.text
    assert r.json()["access_token"]


@pytest.mark.unit
def test_api_key_exchange_rejects_blank_stored_tenant(client: TestClient) -> None:
    """Pre-fix rows with empty tenant_slug must not mint empty-claim JWTs."""
    from digikey.db import session_factory
    from digikey.db_schema import ApiKeyRow
    from digikey.key_crypto import generate_raw_key, hash_secret

    raw, prefix = generate_raw_key()
    sf = session_factory()
    with sf() as session:
        session.add(
            ApiKeyRow(
                key_hash=hash_secret(raw),
                key_prefix=prefix,
                tenant_slug="",
                scopes=["digigraph:chat"],
                kind="standard",
                label="legacy-blank",
            )
        )
        session.commit()

    r = client.post(
        "/v1/oauth/token",
        json={"grant_type": "api_key", "api_key": raw},
    )
    assert r.status_code == 400
    body = r.json()
    msg = (body.get("detail") or body.get("error", {}).get("message") or "").lower()
    assert "blank" in msg
