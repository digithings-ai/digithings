"""A requested ``prefix:*`` must not upgrade a narrower grant at token exchange.

``/v1/oauth/token`` issues ``requested_scopes`` verbatim once
``scope_grants_required(granted, requested)`` is true. The old reverse match in
``digikey.scopes._one_required`` treated a granted ``digivault:read`` as covering
a requested ``digivault:*``, so a read-only API key (or the BFF session, which
holds ``digivault:read`` by default) could mint ``digivault:*`` and then pass the
``digivault:write`` gate. The match is generic, so ``digisearch:query`` reached
``digisearch:*`` and ``digisearch:ingest`` the same way.
"""

from __future__ import annotations

import pytest
from digikey.scopes import scope_grants_required
from fastapi.testclient import TestClient

jwt = pytest.importorskip("jwt")

pytestmark = pytest.mark.unit

ADMIN_TOKEN = "admin-secret-for-wildcard-upgrade"
BFF_TOKEN = "bff-secret-for-wildcard-upgrade"

# (narrow grant, sibling it must not reach, wildcard it must not mint)
NARROW = [
    ("digivault:read", "digivault:write", "digivault:*"),
    ("digisearch:query", "digisearch:ingest", "digisearch:*"),
]


@pytest.mark.parametrize(("narrow", "sibling", "wildcard"), NARROW)
def test_narrow_grant_does_not_cover_wildcard_or_sibling(narrow, sibling, wildcard):
    assert not scope_grants_required([narrow], [wildcard])
    assert not scope_grants_required([narrow], [sibling])
    assert not scope_grants_required([narrow], [f" {wildcard} "])


@pytest.mark.parametrize(("narrow", "sibling", "wildcard"), NARROW)
def test_wildcard_and_exact_holders_still_work(narrow, sibling, wildcard):
    assert scope_grants_required([wildcard], [wildcard])
    assert scope_grants_required([wildcard], [sibling])
    assert scope_grants_required([wildcard], [narrow, sibling])
    assert scope_grants_required(["*"], [wildcard])
    assert scope_grants_required([narrow], [narrow])
    assert scope_grants_required([narrow, sibling], [narrow, sibling])


def test_other_wildcard_shapes_are_not_granted_by_a_read():
    granted = ["digivault:read"]
    for shape in ("*", "digivault:*:*", "digivault:read:*", "DIGIVAULT:*", "digivault"):
        assert not scope_grants_required(granted, [shape]), shape


@pytest.fixture()
def client(monkeypatch, tmp_path):
    monkeypatch.setenv("DIGIKEY_DATABASE_URL", f"sqlite:///{tmp_path / 'dk.db'}")
    monkeypatch.setenv("DIGIKEY_ALLOW_EPHEMERAL_KEY", "1")
    monkeypatch.setenv("DIGIKEY_ADMIN_TOKEN", ADMIN_TOKEN)
    monkeypatch.setenv("DIGIKEY_BFF_TOKEN", BFF_TOKEN)
    monkeypatch.delenv("DIGIKEY_ALLOW_DEV_GLOBAL", raising=False)
    monkeypatch.delenv("DIGIKEY_LITELLM_PROXY_KEY", raising=False)

    from digikey import db

    db._engine = None
    db._session_factory = None

    from digikey.server import app

    with TestClient(app) as c:
        yield c


def _issue_key(client: TestClient, scopes: list[str]) -> str:
    r = client.post(
        "/v1/admin/keys",
        json={"tenant_slug": "tenant-a", "label": "wildcard-upgrade", "scopes": scopes},
        headers={"Authorization": f"Bearer {ADMIN_TOKEN}"},
    )
    assert r.status_code == 200, r.text
    return r.json()["api_key"]


def _exchange_key(client: TestClient, api_key: str, requested: list[str]):
    return client.post(
        "/v1/oauth/token",
        json={"grant_type": "api_key", "api_key": api_key, "requested_scopes": requested},
    )


def _exchange_bff(client: TestClient, requested: list[str]):
    return client.post(
        "/v1/oauth/token",
        headers={"Authorization": f"Bearer {BFF_TOKEN}"},
        json={
            "grant_type": "bff_session",
            "tenant_slug": "tenant-a",
            "subject": "user-1",
            "requested_scopes": requested,
        },
    )


def _scopes(resp) -> list[str]:
    token = resp.json()["access_token"]
    return jwt.decode(token, options={"verify_signature": False})["scopes"]


@pytest.mark.parametrize(("narrow", "sibling", "wildcard"), NARROW)
def test_api_key_exchange_refuses_wildcard_upgrade(client, narrow, sibling, wildcard):
    key = _issue_key(client, [narrow])
    assert _exchange_key(client, key, [wildcard]).status_code == 400
    assert _exchange_key(client, key, [sibling]).status_code == 400
    ok = _exchange_key(client, key, [narrow])
    assert ok.status_code == 200, ok.text
    assert _scopes(ok) == [narrow]


@pytest.mark.parametrize(("narrow", "sibling", "wildcard"), NARROW)
def test_api_key_exchange_keeps_wildcard_holders(client, narrow, sibling, wildcard):
    key = _issue_key(client, [wildcard])
    for requested in ([wildcard], [sibling], [narrow]):
        r = _exchange_key(client, key, requested)
        assert r.status_code == 200, r.text
        assert _scopes(r) == requested
        assert scope_grants_required(_scopes(r), requested)


@pytest.mark.parametrize("wildcard", ["digivault:*", "digisearch:*"])
def test_bff_exchange_refuses_wildcard_upgrade(client, wildcard):
    r = _exchange_bff(client, [wildcard])
    assert r.status_code == 400, r.text
    assert _exchange_bff(client, ["digivault:write"]).status_code == 400


def test_bff_exchange_still_downscopes_to_exact_defaults(client):
    r = _exchange_bff(client, ["digivault:read", "digisearch:query"])
    assert r.status_code == 200, r.text
    scopes = _scopes(r)
    assert scopes == ["digivault:read", "digisearch:query"]
    assert not scope_grants_required(scopes, ["digivault:write"])
