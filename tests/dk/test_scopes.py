"""digikey scope matching.

Covers the ``digisearch:screen`` scope for the digisearch screening path
(DIG-1177): the screening route must need its own scope instead of the
``digisearch:query`` fallthrough, and the BFF session must hand that scope to
digichat without digichat asking for it.
"""

from __future__ import annotations

from pathlib import Path

import pytest
from digikey.scopes import DEFAULT_BFF_SESSION_SCOPES, scope_grants_required
from fastapi.testclient import TestClient

pytestmark = pytest.mark.unit

SCREEN_SCOPE = "digisearch:screen"
SCREEN_PATH = "/internal/art9/screen"

#: The digichat BFF exchange that inherits DEFAULT_BFF_SESSION_SCOPES.
_DIGICHAT_LIB = Path(__file__).resolve().parents[2] / "apps/digichat/src/lib"
DIGICHAT_EXCHANGE_SOURCE = _DIGICHAT_LIB / "digikey-exchange.ts"


def test_star_grants_all():
    assert scope_grants_required(["*"], ["digigraph:chat", "digiquant:backtest"])


def test_exact_scope():
    assert scope_grants_required(["digigraph:chat"], ["digigraph:chat"])
    assert not scope_grants_required(["digigraph:chat"], ["digiquant:backtest"])


def test_prefix_wildcard():
    assert scope_grants_required(["digigraph:*"], ["digigraph:chat", "digigraph:workflow"])
    assert not scope_grants_required(["digigraph:*"], ["digiquant:backtest"])


def test_requested_wildcard_does_not_upgrade_a_read_grant():
    """A requested prefix:* is not a subset of a plain read.

    Token exchange issues the requested scopes when this returns True, so the
    old reverse match let digivault:read mint digivault:* and then satisfy
    digivault:write.
    """
    granted = ["digivault:read"]
    assert not scope_grants_required(granted, ["digivault:*"])
    assert not scope_grants_required(granted, ["digivault:write"])
    assert scope_grants_required(["digivault:*"], ["digivault:write"])
    assert scope_grants_required(["digivault:*"], ["digivault:*"])


def test_run_pipeline_dual():
    req = ["digiquant:backtest", "digiquant:optimize"]
    assert scope_grants_required(["*"], req)
    assert scope_grants_required(["digiquant:backtest", "digiquant:optimize"], req)
    assert not scope_grants_required(["digiquant:backtest"], req)


def test_default_bff_session_scopes_include_digivault_read():
    """digichat BFF JWT must include vault read for MCP vault tools."""
    assert "digivault:read" in DEFAULT_BFF_SESSION_SCOPES


# --- digisearch:screen (DIG-1177) ------------------------------------------------


def _screen_app():
    """A digisearch-shaped app whose routes the real digisearch resolver guards."""
    from digikey.integrations.service_middleware import (
        attach_digi_auth_middleware,
        digisearch_path_scopes,
    )
    from fastapi import FastAPI

    app = FastAPI()
    attach_digi_auth_middleware(app, service="digisearch", path_scopes=digisearch_path_scopes)

    @app.post(SCREEN_PATH)
    def _screen():
        return {"ok": True}

    @app.post("/query")
    def _query():
        return {"ok": True}

    return app


def _token_with_scopes(monkeypatch, scopes: list[str]) -> str:
    """Sign a JWT carrying exactly ``scopes`` against a fresh key."""
    from cryptography.hazmat.primitives import serialization
    from cryptography.hazmat.primitives.asymmetric import rsa
    from digikey.crypto_keys import private_key_to_pem, public_key_to_pem
    from digikey.jwt_issue import issue_access_token

    key = rsa.generate_private_key(public_exponent=65537, key_size=2048)
    monkeypatch.setenv("DIGIKEY_ISSUER", "http://test-dk")
    monkeypatch.setenv("DIGIKEY_AUDIENCE", "digi-ecosystem")
    monkeypatch.setenv("DIGIKEY_PUBLIC_KEY_PEM", public_key_to_pem(key.public_key()))
    monkeypatch.delenv("DIGIKEY_JWKS_URL", raising=False)
    monkeypatch.delenv("DIGIKEY_BLOCKLIST_REDIS_URL", raising=False)

    from digikey import blocklist

    blocklist.reset_client_cache()

    priv = serialization.load_pem_private_key(private_key_to_pem(key).encode(), password=None)
    token, _jti = issue_access_token(
        priv,
        kid="t1",
        sub="bff:user-1",
        tenant_slug="acme",
        scopes=scopes,
        key_pub=None,
        principal_kind="bff_session",
    )
    return token


def test_screen_path_needs_the_screen_scope(monkeypatch):
    """Required test 1a: a session with only digisearch:screen reaches the screen path."""
    token = _token_with_scopes(monkeypatch, [SCREEN_SCOPE])
    client = TestClient(_screen_app())

    r = client.post(SCREEN_PATH, headers={"Authorization": f"Bearer {token}"})

    assert r.status_code == 200, r.text


def test_query_scope_alone_does_not_reach_the_screen_path(monkeypatch):
    """Required test 1b: digisearch:query must not open the screening path."""
    token = _token_with_scopes(monkeypatch, ["digisearch:query"])
    client = TestClient(_screen_app())

    r = client.post(SCREEN_PATH, headers={"Authorization": f"Bearer {token}"})

    assert r.status_code == 403, r.text
    assert r.json()["code"] == "insufficient_scope"


def test_screen_path_is_not_public():
    """The screening path stays behind DigiAuthMiddleware — never auth-exempt."""
    from digikey.integrations.service_middleware import digisearch_path_scopes

    assert digisearch_path_scopes("POST", SCREEN_PATH) == [SCREEN_SCOPE]


@pytest.mark.parametrize(
    ("method", "path", "expected"),
    [
        ("POST", "/query", ["digisearch:query"]),
        ("POST", "/v1/research_turn", ["digisearch:query"]),
        ("GET", "/indexes", ["digisearch:query"]),
        ("POST", "/ingest", ["digisearch:ingest"]),
        ("GET", "/healthz", None),
    ],
)
def test_screen_scope_does_not_widen_other_routes(method, path, expected):
    """Required test 3: existing digisearch routes keep their resolved scopes."""
    from digikey.integrations.service_middleware import digisearch_path_scopes

    assert digisearch_path_scopes(method, path) == expected


# --- digichat inheritance (DIG-1177) ----------------------------------------------

BFF_TOKEN = "test-bff-token-for-screen-scope"
ADMIN_TOKEN = "admin-secret-for-screen-scope"


@pytest.fixture()
def bff_client(monkeypatch, tmp_path):
    """TestClient for digikey with a BFF token and an isolated sqlite store."""
    fakeredis = pytest.importorskip("fakeredis")

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
        yield c


def test_bff_session_scope_list_contains_screen():
    """Required test 2a: the default BFF scope list carries digisearch:screen."""
    assert SCREEN_SCOPE in DEFAULT_BFF_SESSION_SCOPES


def test_digichat_caller_inherits_screen_scope_without_requesting_it(bff_client):
    """Required test 2b: digichat sends no requested_scopes and still gets the scope.

    ``exchangeDigikeyBffSession`` in ``apps/digichat/src/lib/digikey-exchange.ts``
    posts only ``grant_type``/``tenant_slug``/``subject``, so the session must
    resolve to the full default list. The inheritance is the design — assert it
    against the real exchange rather than assuming it.
    """
    jwt = pytest.importorskip("jwt")

    r = bff_client.post(
        "/v1/oauth/token",
        headers={"Authorization": f"Bearer {BFF_TOKEN}"},
        # Same body digichat sends: no requested_scopes key at all.
        json={"grant_type": "bff_session", "tenant_slug": "acme", "subject": "alice"},
    )
    assert r.status_code == 200, r.text

    claims = jwt.decode(r.json()["access_token"], options={"verify_signature": False})
    assert SCREEN_SCOPE in claims["scopes"]


def test_digichat_exchange_source_sends_no_requested_scopes():
    """Guard the inheritance: digichat must keep sending no requested_scopes.

    If digichat ever sends ``requested_scopes``, it replaces the default list and
    loses digisearch:screen. This test fails loudly so the coupling is visible.
    """
    text = DIGICHAT_EXCHANGE_SOURCE.read_text(encoding="utf-8")
    start = text.index("export async function exchangeDigikeyBffSession")
    body = text[start : text.index("\n}", start)]

    assert "requested_scopes" not in body, (
        "digichat now sends requested_scopes; it will drop digisearch:screen "
        "from the BFF session and needs the scope listed explicitly"
    )


def test_screen_scope_is_not_requestable_on_its_own_via_bff_session(bff_client):
    """A bff_session may only narrow to a subset, never widen past the defaults."""
    r = bff_client.post(
        "/v1/oauth/token",
        headers={"Authorization": f"Bearer {BFF_TOKEN}"},
        json={
            "grant_type": "bff_session",
            "tenant_slug": "acme",
            "subject": "alice",
            "requested_scopes": [SCREEN_SCOPE, "digisearch:screen:admin"],
        },
    )
    assert r.status_code == 400
    assert "requested_scopes not allowed" in r.text
