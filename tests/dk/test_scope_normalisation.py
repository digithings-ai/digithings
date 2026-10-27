"""``requested_scopes`` are normalised before they reach the JWT claim (DIG-5723).

``/v1/oauth/token`` assigned the caller's list verbatim, so a padded scope
(``" mcp:digisearch"``) or a duplicate landed in the space-delimited ``scope``
claim as written. The grant check already stripped, so the padded entry passed
the check and then minted a different token on the wire. These tests pin the
normalisation at both exchanges (``bff_session`` and ``api_key``) and at admin
key issuance.
"""

from __future__ import annotations

import pytest
from digikey.scopes import MCP_DIGIVAULT_WRITE_SCOPE
from fastapi.testclient import TestClient

jwt = pytest.importorskip("jwt")

pytestmark = pytest.mark.unit

ADMIN_TOKEN = "admin-secret-for-scope-normalisation"
BFF_TOKEN = "bff-secret-for-scope-normalisation"


def _claims(resp) -> dict:
    token = resp.json()["access_token"]
    return jwt.decode(token, options={"verify_signature": False})


@pytest.fixture()
def client(monkeypatch, tmp_path):
    monkeypatch.setenv("DIGIKEY_DATABASE_URL", f"sqlite:///{tmp_path / 'dk.db'}")
    monkeypatch.setenv("DIGIKEY_ALLOW_EPHEMERAL_KEY", "1")
    monkeypatch.setenv("DIGIKEY_ADMIN_TOKEN", ADMIN_TOKEN)
    monkeypatch.setenv("DIGIKEY_BFF_TOKEN", BFF_TOKEN)
    monkeypatch.delenv("DIGIKEY_BLOCKLIST_REDIS_URL", raising=False)
    monkeypatch.delenv("DIGIKEY_LITELLM_PROXY_KEY", raising=False)

    from digikey import db

    db._engine = None
    db._session_factory = None

    from digikey.server import app

    with TestClient(app) as c:
        yield c


def _bff_exchange(client: TestClient, requested: list[str]):
    return client.post(
        "/v1/oauth/token",
        headers={"Authorization": f"Bearer {BFF_TOKEN}"},
        json={
            "grant_type": "bff_session",
            "tenant_slug": "acme",
            "subject": "alice",
            "requested_scopes": requested,
        },
    )


def _issue_key(client: TestClient, scopes: list[str]):
    return client.post(
        "/v1/admin/keys",
        json={"tenant_slug": "acme", "label": "normalisation", "scopes": scopes},
        headers={"Authorization": f"Bearer {ADMIN_TOKEN}"},
    )


def _exchange_key(client: TestClient, api_key: str, requested: list[str]):
    return client.post(
        "/v1/oauth/token",
        json={"grant_type": "api_key", "api_key": api_key, "requested_scopes": requested},
    )


def test_bff_strips_and_dedupes_requested_scopes(client):
    r = _bff_exchange(client, [" mcp:digisearch ", "mcp:digisearch", " mcp:digivault"])
    assert r.status_code == 200, r.text

    claims = _claims(r)
    assert claims["scopes"] == ["mcp:digisearch", "mcp:digivault"]
    assert claims["scope"] == "mcp:digisearch mcp:digivault"


def test_bff_refuses_an_all_blank_requested_list(client):
    r = _bff_exchange(client, ["   ", "\t"])

    assert r.status_code == 400, r.text
    assert "must not be blank" in r.text


def test_bff_refuses_one_entry_that_hides_two_scopes(client):
    """Inner whitespace is two scopes on the wire; refuse rather than smuggle."""
    r = _bff_exchange(client, ["mcp:digisearch mcp:digivault:write"])

    assert r.status_code == 400, r.text
    assert "invalid scope" in r.text


def test_bff_still_cannot_ask_for_the_mcp_vault_write_scope(client):
    """`mcp:digivault` is read-only; only an admin-issued key may write."""
    r = _bff_exchange(client, ["mcp:digivault", MCP_DIGIVAULT_WRITE_SCOPE])

    assert r.status_code == 400, r.text
    assert "requested_scopes not allowed" in r.text


def test_api_key_issuance_strips_and_dedupes_scopes(client):
    issued = _issue_key(client, [" digivault:read ", "digivault:read"])
    assert issued.status_code == 200, issued.text

    # No requested_scopes: the exchange mints the stored key scopes, so this
    # reads back what the admin call actually persisted.
    r = client.post(
        "/v1/oauth/token", json={"grant_type": "api_key", "api_key": issued.json()["api_key"]}
    )
    assert r.status_code == 200, r.text
    assert _claims(r)["scopes"] == ["digivault:read"]


def test_api_key_issuance_refuses_inner_whitespace(client):
    r = _issue_key(client, ["digivault:read digivault:write"])

    assert r.status_code == 400, r.text
    assert "invalid scope" in r.text


def test_api_key_exchange_strips_and_dedupes_requested_scopes(client):
    issued = _issue_key(client, ["digivault:read"])
    assert issued.status_code == 200, issued.text

    r = _exchange_key(client, issued.json()["api_key"], [" digivault:read ", "digivault:read"])

    assert r.status_code == 200, r.text
    claims = _claims(r)
    assert claims["scopes"] == ["digivault:read"]
    assert claims["scope"] == "digivault:read"


def test_api_key_exchange_refuses_an_all_blank_requested_list(client):
    issued = _issue_key(client, ["digivault:read"])
    assert issued.status_code == 200, issued.text

    r = _exchange_key(client, issued.json()["api_key"], ["  "])

    assert r.status_code == 400, r.text
    assert "must not be blank" in r.text
