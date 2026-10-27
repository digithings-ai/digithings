"""Tenant-scoped indexes answer only their own verified tenant (DIG-3585).

The map below has the shape the stack composes into the container's
``DIGI_TENANT_CORPUS_MAP``: the house tenant owns the public docs corpus, a
second tenant owns its help corpus plus a per-tool ticket index. Slugs and
index names are fixtures; only the shape matters.
"""

from __future__ import annotations

import json

import pytest
from digisearch.core.models import Chunk, Query
from digisearch.indexes.backends.vectorize import VectorizeBackend
from digisearch.search import add_chunks
from digisearch.search._stub import query_index
from digisearch.server import app
from digisearch.tenant_index_scope import (
    IndexNotPermitted,
    InvalidIndexName,
    TenantIndexMapError,
    check_indexes,
    load_scoped_indexes,
    parse_index_list,
    validate_index_name,
    verified_tenant_from_bearer,
)
from fastapi.testclient import TestClient
from mcp.server.fastmcp.exceptions import ToolError

from digisearch import mcp_server, tenant_index_scope
from tests.digi_test_jwt import auth_headers, mint_test_jwt

pytestmark = pytest.mark.unit

TENANT = "tenant-a"
HOUSE = "digithings"
HELP_INDEX = "tenant_a_help"
TICKETS_INDEX = "tenant-a-tickets"
HOUSE_INDEX = "digithings_docs"

CORPUS_MAP = json.dumps(
    {
        HOUSE: {"digisearchIndex": HOUSE_INDEX, "vaultPathPrefix": "clients/digithings"},
        TENANT: {
            "digisearchIndex": HELP_INDEX,
            "digisearchTools": {
                "search_tenant_a_tickets": {"index": TICKETS_INDEX, "description": "t"},
                "search_tenant_a_help": {"index": HELP_INDEX, "description": "h"},
            },
            "vaultPathPrefix": "clients/tenant-a",
        },
    }
)


@pytest.fixture
def scoped_map(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("DIGI_TENANT_CORPUS_MAP", CORPUS_MAP)
    monkeypatch.delenv("DIGISEARCH_PUBLIC_TENANTS", raising=False)


@pytest.fixture
def seeded() -> None:
    for idx in (HELP_INDEX, TICKETS_INDEX, HOUSE_INDEX):
        add_chunks(
            idx,
            [
                Chunk(
                    id=f"{idx}-1",
                    content=f"scope fixture document in {idx}",
                    doc_id=f"{idx}-doc",
                    embedding=None,
                    metadata={},
                )
            ],
        )


def _client(tenant: str) -> TestClient:
    return TestClient(app, headers=auth_headers(tenant_slug=tenant))


# --- the map --------------------------------------------------------------------


def test_unset_map_scopes_nothing(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.delenv("DIGI_TENANT_CORPUS_MAP", raising=False)
    assert load_scoped_indexes() == {}
    check_indexes([HELP_INDEX], None)


def test_map_scopes_tenant_indexes_and_leaves_the_house_docs_public(scoped_map: None) -> None:
    scoped = load_scoped_indexes()
    assert scoped == {"tenant_a_help": frozenset({TENANT}), "tenant_a_tickets": frozenset({TENANT})}


@pytest.mark.parametrize("raw", ["{not json", "[]", '{"x": 1}'])
def test_a_set_but_broken_map_is_an_error_not_unset(raw: str) -> None:
    with pytest.raises(TenantIndexMapError):
        load_scoped_indexes(raw)


@pytest.mark.parametrize(
    "name", ["TENANT_A_HELP", "tenant_a_tickets", "Tenant-A-Tickets", f"{HOUSE_INDEX},{HELP_INDEX}"]
)
def test_spelling_variants_and_comma_lists_are_refused(scoped_map: None, name: str) -> None:
    with pytest.raises(IndexNotPermitted):
        check_indexes([name], HOUSE)
    check_indexes([name], TENANT)


# --- POST /query ----------------------------------------------------------------


def test_query_serves_a_tenant_index_to_its_own_verified_tenant(
    scoped_map: None, seeded: None
) -> None:
    r = _client(TENANT).post("/query", json={"text": "scope fixture", "index_name": HELP_INDEX})
    assert r.status_code == 200, r.text
    assert r.json()["results"]


@pytest.mark.parametrize("index_name", [HELP_INDEX, TICKETS_INDEX, f"{HOUSE_INDEX},{HELP_INDEX}"])
def test_query_refuses_a_tenant_index_to_another_tenant(
    scoped_map: None, seeded: None, index_name: str
) -> None:
    r = _client("pytest-tenant").post(
        "/query", json={"text": "scope fixture", "index_name": index_name}
    )
    assert r.status_code == 403, r.text


def test_query_ignores_an_unsigned_tenant_header(scoped_map: None, seeded: None) -> None:
    """A token with no tenant claim plus ``X-Digi-Tenant`` naming the tenant is not the tenant (#2303)."""
    client = TestClient(
        app,
        headers={**auth_headers(tenant_slug=""), "X-Digi-Tenant": TENANT},
    )
    r = client.post("/query", json={"text": "scope fixture", "index_name": HELP_INDEX})
    assert r.status_code == 403, r.text


def test_query_keeps_the_house_docs_open_to_every_caller(scoped_map: None, seeded: None) -> None:
    r = _client("pytest-tenant").post(
        "/query", json={"text": "scope fixture", "index_name": HOUSE_INDEX}
    )
    assert r.status_code == 200, r.text


def test_query_is_unchanged_without_a_map(monkeypatch: pytest.MonkeyPatch, seeded: None) -> None:
    monkeypatch.delenv("DIGI_TENANT_CORPUS_MAP", raising=False)
    r = _client("pytest-tenant").post(
        "/query", json={"text": "scope fixture", "index_name": HELP_INDEX}
    )
    assert r.status_code == 200, r.text


def test_query_fails_closed_on_a_broken_map(monkeypatch: pytest.MonkeyPatch, seeded: None) -> None:
    monkeypatch.setenv("DIGI_TENANT_CORPUS_MAP", "{not json")
    r = _client(TENANT).post("/query", json={"text": "scope fixture", "index_name": HELP_INDEX})
    assert r.status_code == 503, r.text


# --- POST /v1/orchestrator_invoke: the path digigraph uses for a tenant chat ----


def test_the_tenant_chat_search_through_digigraph_still_works(
    scoped_map: None, seeded: None
) -> None:
    """digigraph forwards the chat's tenant JWT and pins the index from the map."""
    client = _client(TENANT)
    for tool, idx in (("digisearch", HELP_INDEX), ("digisearch", TICKETS_INDEX)):
        r = client.post(
            "/v1/orchestrator_invoke",
            json={"tool": tool, "arguments": {"query": "scope fixture", "index_name": idx}},
        )
        assert r.status_code == 200, r.text
        assert r.json()["ok"] is True
    r = client.post(
        "/v1/orchestrator_invoke",
        json={
            "tool": "digisearch_fetch_all",
            "arguments": {"query": "scope fixture"},
            "default_index_name": HELP_INDEX,
        },
    )
    assert r.status_code == 200, r.text
    assert r.json()["ok"] is True


@pytest.mark.parametrize(
    ("tool", "arguments"),
    [
        ("digisearch", {"query": "scope fixture", "index_name": HELP_INDEX}),
        ("digisearch_fetch_all", {"query": "scope fixture", "index_name": TICKETS_INDEX}),
        (
            "digisearch_research_delegate",
            {"user_message": "scope fixture", "index_name": HELP_INDEX},
        ),
    ],
)
def test_orchestrator_invoke_refuses_another_tenants_index(
    scoped_map: None, seeded: None, tool: str, arguments: dict
) -> None:
    r = _client(HOUSE).post("/v1/orchestrator_invoke", json={"tool": tool, "arguments": arguments})
    assert r.status_code == 403, r.text


def test_orchestrator_invoke_checks_the_default_index_too(scoped_map: None, seeded: None) -> None:
    r = _client(HOUSE).post(
        "/v1/orchestrator_invoke",
        json={
            "tool": "digisearch",
            "arguments": {"query": "scope fixture"},
            "default_index_name": HELP_INDEX,
        },
    )
    assert r.status_code == 403, r.text


def test_research_turn_refuses_another_tenants_index(scoped_map: None) -> None:
    r = _client(HOUSE).post(
        "/v1/research_turn", json={"user_message": "scope fixture", "index_name": HELP_INDEX}
    )
    assert r.status_code == 403, r.text


# --- the MCP tools --------------------------------------------------------------


@pytest.fixture
def mcp_bearer(monkeypatch: pytest.MonkeyPatch):
    """Point the MCP guard at a chosen Authorization header."""

    def use(header: str | None) -> None:
        monkeypatch.setattr(mcp_server, "_mcp_authorization_header", lambda: header)

    return use


def _call_semantic(index_name: str) -> str:
    fn = mcp_server.semantic
    return fn(text="scope fixture", index_name=index_name)


def test_mcp_serves_a_tenant_index_to_its_own_verified_tenant(
    scoped_map: None, seeded: None, mcp_bearer, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setenv("DIGISEARCH_ALLOW_STUB", "1")
    mcp_bearer(f"Bearer {mint_test_jwt(tenant_slug=TENANT)}")
    assert "scope fixture" in _call_semantic(HELP_INDEX)


@pytest.mark.parametrize(
    "header",
    [None, "", "Bearer not-a-jwt", "house"],
    ids=["no-request", "empty", "garbage", "house-tenant"],
)
def test_mcp_refuses_a_tenant_index_without_that_verified_tenant(
    scoped_map: None, mcp_bearer, header: str | None
) -> None:
    if header == "house":
        header = f"Bearer {mint_test_jwt(tenant_slug=HOUSE)}"
    mcp_bearer(header)
    for call in (
        lambda: _call_semantic(HELP_INDEX),
        lambda: _call_semantic(TICKETS_INDEX),
        lambda: mcp_server.search_strategies(query="scope fixture", index_name=HELP_INDEX),
    ):
        with pytest.raises(ToolError, match="not available"):
            call()


def test_mcp_research_turn_refuses_a_tenant_index(scoped_map: None, mcp_bearer) -> None:
    mcp_bearer(None)
    with pytest.raises(ToolError, match="not available"):
        mcp_server.research_turn(user_message="scope fixture", index_name=HELP_INDEX)


def test_mcp_does_not_verify_a_bearer_for_a_public_index(
    scoped_map: None, seeded: None, mcp_bearer, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setenv("DIGISEARCH_ALLOW_STUB", "1")
    mcp_bearer(None)

    def boom(_header: str | None) -> str | None:
        raise AssertionError("public index must not need a verified tenant")

    monkeypatch.setattr(mcp_server, "verified_tenant_from_bearer", boom)
    assert "scope fixture" in _call_semantic(HOUSE_INDEX)


def test_mcp_reads_the_bearer_from_the_real_http_request(
    scoped_map: None, seeded: None, monkeypatch: pytest.MonkeyPatch
) -> None:
    """End to end over streamable HTTP: the guard sees the request's own header."""
    from mcp.server.fastmcp import FastMCP

    monkeypatch.setenv("DIGISEARCH_ALLOW_STUB", "1")
    probe = FastMCP("scope-probe", json_response=True, stateless_http=True)

    @probe.tool()
    def guarded(index_name: str) -> str:
        mcp_server._enforce_mcp_index(index_name)
        return "allowed"

    def call(c: TestClient, header: str | None) -> dict:
        frame = {
            "jsonrpc": "2.0",
            "id": 1,
            "method": "tools/call",
            "params": {"name": "guarded", "arguments": {"index_name": HELP_INDEX}},
        }
        headers = {
            "accept": "application/json, text/event-stream",
            "content-type": "application/json",
        }
        if header:
            headers["authorization"] = header
        r = c.post("/mcp", json=frame, headers=headers)
        assert r.status_code == 200, r.text
        return r.json()["result"]

    with TestClient(probe.streamable_http_app(), base_url="http://127.0.0.1:8765") as c:
        ok = call(c, f"Bearer {mint_test_jwt(tenant_slug=TENANT)}")
        assert ok["isError"] is False and ok["content"][0]["text"] == "allowed"
        refused = call(c, f"Bearer {mint_test_jwt(tenant_slug=HOUSE)}")
        assert refused["isError"] is True and "not available" in refused["content"][0]["text"]
        assert call(c, None)["isError"] is True


def test_the_module_reads_the_map_on_every_call(monkeypatch: pytest.MonkeyPatch) -> None:
    """No import-time cache: a map change takes effect without a restart."""
    monkeypatch.delenv("DIGI_TENANT_CORPUS_MAP", raising=False)
    assert tenant_index_scope.load_scoped_indexes() == {}
    monkeypatch.setenv("DIGI_TENANT_CORPUS_MAP", CORPUS_MAP)
    assert tenant_index_scope.load_scoped_indexes()


# --- index-name allowlist -----------------------------------------------------------

#: Names that must never reach a backend: path segments, URL syntax, escapes,
#: blank comma lists, and names outside ``[a-z0-9][a-z0-9_-]{0,63}``.
BAD_NAMES = [
    "x/../name",
    "./name",
    "name/query?",
    "name/query#",
    "%2D",
    "tenant%2Da",
    "..",
    "name/",
    "na me",
    "_leading",
    "-leading",
    "name.with.dots",
    "a" * 65,
    "",
    " ",
    " , ",
    ",",
    ", ,",
    f"{HOUSE_INDEX},x/../{HELP_INDEX}",
]
BAD_IDS = [
    "dotdot-path",
    "dot-slash",
    "query-qmark",
    "query-hash",
    "pct-2D",
    "pct-inside",
    "dotdot",
    "trailing-slash",
    "space",
    "leading-underscore",
    "leading-dash",
    "dots",
    "too-long",
    "empty",
    "blank",
    "blank-list",
    "comma",
    "commas",
    "bad-entry-in-list",
]


@pytest.mark.parametrize("name", BAD_NAMES, ids=BAD_IDS)
def test_parse_index_list_refuses_anything_but_plain_names(name: str) -> None:
    with pytest.raises(InvalidIndexName):
        parse_index_list(name)


@pytest.mark.parametrize(
    "name",
    ["default", HOUSE_INDEX, HELP_INDEX, TICKETS_INDEX, "Tenant-A-Tickets", "a", "0", "a" * 64],
)
def test_plain_names_pass(name: str) -> None:
    assert validate_index_name(f" {name} ") == name


def test_a_comma_list_of_plain_names_passes() -> None:
    assert parse_index_list(f"{HOUSE_INDEX}, {HELP_INDEX}") == [HOUSE_INDEX, HELP_INDEX]
    # Empty entries beside a real name are dropped, as before; only a list
    # with no name at all is refused.
    assert parse_index_list(f"{HOUSE_INDEX},, ,") == [HOUSE_INDEX]


@pytest.mark.parametrize("name", BAD_NAMES, ids=BAD_IDS)
def test_check_indexes_refuses_malformed_names_with_or_without_a_map(
    monkeypatch: pytest.MonkeyPatch, name: str
) -> None:
    monkeypatch.delenv("DIGI_TENANT_CORPUS_MAP", raising=False)
    with pytest.raises(InvalidIndexName):
        check_indexes([name], TENANT)
    with pytest.raises(InvalidIndexName):
        check_indexes([name], TENANT, raw_map=CORPUS_MAP)


@pytest.mark.parametrize("name", BAD_NAMES, ids=BAD_IDS)
def test_query_refuses_a_malformed_index_name(scoped_map: None, name: str) -> None:
    r = _client(TENANT).post("/query", json={"text": "scope fixture", "index_name": name})
    assert r.status_code in (400, 422), r.text


@pytest.mark.parametrize("name", BAD_NAMES, ids=BAD_IDS)
def test_research_turn_refuses_a_malformed_index_name(scoped_map: None, name: str) -> None:
    r = _client(TENANT).post(
        "/v1/research_turn", json={"user_message": "scope fixture", "index_name": name}
    )
    assert r.status_code in (400, 422), r.text


@pytest.mark.parametrize(
    "tool,key",
    [
        ("digisearch", "query"),
        ("digisearch_fetch_all", "query"),
        ("digisearch_research_delegate", "user_message"),
    ],
)
@pytest.mark.parametrize(
    "name", ["x/../name", "./name", "name/query?", "name/query#", "%2D", " , "]
)
def test_orchestrator_invoke_refuses_a_malformed_index_name_with_400(
    scoped_map: None, tool: str, key: str, name: str
) -> None:
    r = _client(TENANT).post(
        "/v1/orchestrator_invoke",
        json={"tool": tool, "arguments": {key: "scope fixture", "index_name": name}},
    )
    assert r.status_code == 400, r.text


def test_orchestrator_invoke_refuses_a_malformed_default_index(scoped_map: None) -> None:
    r = _client(TENANT).post(
        "/v1/orchestrator_invoke",
        json={
            "tool": "digisearch",
            "arguments": {"query": "scope fixture"},
            "default_index_name": "x/../name",
        },
    )
    assert r.status_code == 422, r.text


def test_orchestrator_invoke_refuses_a_non_string_index(scoped_map: None) -> None:
    r = _client(TENANT).post(
        "/v1/orchestrator_invoke",
        json={"tool": "digisearch", "arguments": {"query": "scope fixture", "index_name": 7}},
    )
    assert r.status_code == 400, r.text


@pytest.mark.parametrize(
    "name", ["x/../name", "./name", "name/query?", "name/query#", "%2D", " , "]
)
def test_mcp_refuses_a_malformed_index_name(mcp_bearer, name: str) -> None:
    mcp_bearer(f"Bearer {mint_test_jwt(tenant_slug=TENANT)}")
    with pytest.raises(ToolError, match="invalid index name"):
        _call_semantic(name)


@pytest.mark.parametrize("name", [" , ", ",", "x/../name", "%2D"])
def test_query_index_never_falls_back_to_the_default_for_a_bad_list(name: str) -> None:
    with pytest.raises(InvalidIndexName):
        query_index(Query(text="scope fixture", top_k=1), index_name=name)


@pytest.mark.parametrize("name", ["x/../name", "./name", "name/query?", "name/query#", "%2D"])
def test_vectorize_backend_refuses_a_malformed_name(name: str) -> None:
    with pytest.raises(InvalidIndexName):
        VectorizeBackend(name, account_id="acct", api_token="unused")


def test_vectorize_backend_quotes_the_index_path_segment() -> None:
    backend = VectorizeBackend(TICKETS_INDEX, account_id="acct", api_token="unused")
    assert backend._url("query").endswith(f"/vectorize/v2/indexes/{TICKETS_INDEX}/query")


# --- the MCP bearer gets the middleware's revocation and scope checks -------------------


def test_mcp_bearer_without_the_mcp_scope_has_no_tenant() -> None:
    token = mint_test_jwt(tenant_slug=TENANT, scopes=["digisearch:query"])
    assert verified_tenant_from_bearer(f"Bearer {token}") is None
    token = mint_test_jwt(tenant_slug=TENANT, scopes=["mcp:digisearch"])
    assert verified_tenant_from_bearer(f"Bearer {token}") == TENANT


def test_a_revoked_mcp_bearer_has_no_tenant(monkeypatch: pytest.MonkeyPatch) -> None:
    from digikey import blocklist

    monkeypatch.setattr(blocklist, "is_configured", lambda: True)
    monkeypatch.setattr(blocklist, "is_blocked", lambda jti: True)
    assert verified_tenant_from_bearer(f"Bearer {mint_test_jwt(tenant_slug=TENANT)}") is None


def test_an_mcp_bearer_fails_closed_when_the_blocklist_is_unavailable(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    from digikey import blocklist

    def down(jti: str) -> bool:
        raise blocklist.BlocklistUnavailable("down")

    monkeypatch.setattr(blocklist, "is_configured", lambda: True)
    monkeypatch.setattr(blocklist, "is_blocked", down)
    assert verified_tenant_from_bearer(f"Bearer {mint_test_jwt(tenant_slug=TENANT)}") is None


def test_an_mcp_bearer_fails_closed_when_the_blocklist_is_required_but_unset(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    from digikey import blocklist

    monkeypatch.setattr(blocklist, "require_blocklist_enabled", lambda: True)
    monkeypatch.setattr(blocklist, "is_configured", lambda: False)
    assert verified_tenant_from_bearer(f"Bearer {mint_test_jwt(tenant_slug=TENANT)}") is None
