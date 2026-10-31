"""digigraph never takes the tenant from the unsigned X-Digi-Tenant header (DIG-3585).

The tenant that selects a mapped corpus, research prompt, session lock, per-index
tools and skills comes from the signed JWT claim only. A token with no tenant
claim gets nothing tenant-specific (fail closed) whatever header it sends, and a
token with a claim keeps its own tenant against a header naming another one.
The single-tenant path (no map) is unchanged: there the corpus headers still
select the index, and no tenant is involved.
"""

from __future__ import annotations

import json
from types import SimpleNamespace

import pytest
from digigraph.corpus_routing import TenantCorpusOverride, resolve_corpus_override
from digigraph.http_api.context import _digi_fields_from_request
from digikey.integrations.service_middleware import attach_digi_auth_middleware
from digikey.models import DigiAuthContext
from fastapi import FastAPI, Request
from fastapi.testclient import TestClient

from tests.digi_test_jwt import auth_headers

pytestmark = pytest.mark.unit

_MAP = json.dumps(
    {
        "tenant-a": {
            "digisearchIndex": "tenant_a_docs",
            "vaultPathPrefix": "clients/tenant-a",
            "researchSystemPrompt": "tenant-a prompt",
            "lockSessionControls": True,
        },
        "house": {"digisearchIndex": "house_docs", "vaultPathPrefix": "clients/house"},
    }
)

_TENANT_HEADERS = (
    {"x-digi-tenant": "tenant-a"},
    {"X-Digi-Tenant": "tenant-a"},
    {"x-digi-tenant": "TENANT-A "},
)


def _request(auth: DigiAuthContext | None, headers: dict[str, str]) -> SimpleNamespace:
    return SimpleNamespace(
        state=SimpleNamespace(digi_auth=auth, digi_bearer=None),
        headers=headers,
    )


def _claimless() -> DigiAuthContext:
    # What the middleware builds for a verified token with no tenant claim.
    return DigiAuthContext(subject="key:x", tenant_slug="", tenant_slug_verified=False)


def _signed(slug: str) -> DigiAuthContext:
    return DigiAuthContext(subject="key:x", tenant_slug=slug, tenant_slug_verified=True)


def _assert_nothing_tenant_specific(updates: dict) -> None:
    assert updates["digisearch_index"] is None
    assert updates["vault_path_prefix"] is None
    assert updates["research_system_prompt_override"] is None
    assert updates["lock_session_controls"] is False
    assert updates["skill_pack"] is None
    assert updates["skills"] == []
    assert "digi_trace_tenant" not in updates


@pytest.mark.parametrize("headers", _TENANT_HEADERS)
def test_resolve_ignores_the_tenant_header_when_auth_names_no_tenant(headers) -> None:
    table = {"tenant-a": TenantCorpusOverride(digisearch_index="tenant_a_docs")}
    assert resolve_corpus_override(headers=headers, tenant_slug=None, corpus_map=table) == (
        TenantCorpusOverride()
    )


@pytest.mark.parametrize("headers", _TENANT_HEADERS)
def test_claimless_token_with_tenant_header_gets_no_tenant_corpus(
    monkeypatch: pytest.MonkeyPatch, headers
) -> None:
    monkeypatch.setenv("DIGI_TENANT_CORPUS_MAP", _MAP)
    hostile = {
        **headers,
        "x-digi-corpus-index": "tenant_a_docs",
        "x-digi-vault-prefix": "clients/tenant-a",
    }
    _assert_nothing_tenant_specific(_digi_fields_from_request(_request(_claimless(), hostile)))


def test_unverified_tenant_slug_is_not_trusted(monkeypatch: pytest.MonkeyPatch) -> None:
    """A context whose tenant did not come from a signed claim is no tenant."""
    monkeypatch.setenv("DIGI_TENANT_CORPUS_MAP", _MAP)
    auth = DigiAuthContext(subject="key:x", tenant_slug="tenant-a", tenant_slug_verified=False)
    _assert_nothing_tenant_specific(_digi_fields_from_request(_request(auth, {})))


def test_signed_tenant_wins_over_a_header_naming_another(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setenv("DIGI_TENANT_CORPUS_MAP", _MAP)
    updates = _digi_fields_from_request(_request(_signed("house"), {"x-digi-tenant": "tenant-a"}))
    assert updates["digisearch_index"] == "house_docs"
    assert updates["vault_path_prefix"] == "clients/house"
    assert updates["research_system_prompt_override"] is None
    assert updates["lock_session_controls"] is False
    assert updates["digi_trace_tenant"] == "house"


def test_the_tenant_own_signed_claim_still_reaches_its_corpus(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """The invite path: digichat's bff_session JWT carries the tenant claim."""
    monkeypatch.setenv("DIGI_TENANT_CORPUS_MAP", _MAP)
    updates = _digi_fields_from_request(
        _request(_signed("tenant-a"), {"x-digi-tenant": "tenant-a"})
    )
    assert updates["digisearch_index"] == "tenant_a_docs"
    assert updates["vault_path_prefix"] == "clients/tenant-a"
    assert updates["research_system_prompt_override"] == "tenant-a prompt"
    assert updates["lock_session_controls"] is True
    assert updates["digi_trace_tenant"] == "tenant-a"


def test_single_tenant_corpus_headers_are_unchanged() -> None:
    """No map: the corpus headers still pick the index, as before; no tenant involved."""
    headers = {"x-digi-corpus-index": "local_docs", "x-digi-tenant": "tenant-a"}
    out = resolve_corpus_override(headers=headers, tenant_slug=None, corpus_map={})
    assert out.digisearch_index == "local_docs"


def test_middleware_and_context_end_to_end(monkeypatch: pytest.MonkeyPatch) -> None:
    """Real signed JWTs through DigiAuthMiddleware into digigraph's request context."""
    monkeypatch.setenv("DIGI_TENANT_CORPUS_MAP", _MAP)
    app = FastAPI()
    attach_digi_auth_middleware(app, service="digigraph", path_scopes=lambda m, p: [])

    @app.get("/ctx")
    def _ctx(request: Request) -> dict:
        updates = _digi_fields_from_request(request)
        return {"index": updates["digisearch_index"], "prefix": updates["vault_path_prefix"]}

    client = TestClient(app)
    claimless = client.get(
        "/ctx", headers={**auth_headers(tenant_slug=""), "X-Digi-Tenant": "tenant-a"}
    )
    assert claimless.status_code == 200
    assert claimless.json() == {"index": None, "prefix": None}

    own = client.get("/ctx", headers=auth_headers(tenant_slug="tenant-a"))
    assert own.json() == {"index": "tenant_a_docs", "prefix": "clients/tenant-a"}
