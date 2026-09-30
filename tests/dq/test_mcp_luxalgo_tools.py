"""MCP wiring for the LuxAlgo Library thin wrap (#4779 P0).

Wrappers are exercised through FastMCP's tool manager with a
MockTransport-backed LuxAlgoClient patched over the env-seam builder. No
network, no key required (every wrapped tool is ``free``).

Also pinned: the license-boundary absences (``library_get_source_code``,
``broker_*``/``journal_*``/``edge_*`` are never wrapped) and the kill switch.
"""

from __future__ import annotations

import json
from typing import Any

import httpx
import pytest

pytest.importorskip("mcp.server.fastmcp")

pytestmark = pytest.mark.unit

from digiquant.data.luxalgo import (  # noqa: E402
    LUXALGO_ATTRIBUTION,
    LUXALGO_CONTEXT,
    LUXALGO_ENABLED_ENV,
    LUXALGO_LIBRARY_URL,
    LUXALGO_MCP_URL,
    LUXALGO_TOOLS,
    RESEARCH_TOOLS,
    TOOL_ENTITLEMENTS,
    LuxAlgoClient,
    agent_tools,
    available_luxalgo_tools,
    build_luxalgo_tool_dispatcher,
    luxalgo_enabled,
)
from digiquant.mcp_server import READ_SCOPE_TOOLS, create_mcp_server  # noqa: E402
from digiquant.orchestrator_tools import build_orchestrator_tool_manifest  # noqa: E402
from digiquant.server import app  # noqa: E402
from fastapi.testclient import TestClient  # noqa: E402

from digiquant import mcp_server  # noqa: E402
from tests.digi_test_jwt import auth_headers  # noqa: E402

LUXALGO_TOOL_NAMES = {
    "luxalgo_library_search",
    "luxalgo_library_get_concept",
    "luxalgo_library_get_indicator",
    "luxalgo_library_list_concepts",
    "luxalgo_library_list_indicators",
    "luxalgo_library_list_tags",
    "luxalgo_library_list_families",
    "luxalgo_library_get_family",
}

#: Upstream tool names that must NEVER appear on the digiquant surface.
FORBIDDEN_UPSTREAM = {
    "luxalgo_library_get_source_code",
    "library_get_source_code",
    "luxalgo_broker_list",
    "luxalgo_journal_list",
    "luxalgo_edge_list",
}

SEARCH_RESULT = {
    "results": [
        {
            "kind": "concept",
            "slug": "rsi",
            "name": "Relative Strength Index",
            "family": "momentum",
            "url": "https://luxalgo.com/library/rsi/",
            "md_url": "https://luxalgo.com/library/rsi.md",
        }
    ],
    "total": 1,
}

CONCEPT_RESULT = {
    "slug": "rsi",
    "name": "Relative Strength Index",
    "family": "momentum",
    "url": "https://luxalgo.com/library/rsi/",
    "md_url": "https://luxalgo.com/library/rsi.md",
    "aliases": ["relative-strength-index"],
    "content_markdown": "# RSI\nMomentum oscillator.",
}


@pytest.fixture(autouse=True)
def clean_env(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.delenv(LUXALGO_ENABLED_ENV, raising=False)


def _mcp(name: str):
    return create_mcp_server()._tool_manager.get_tool(name).fn


def _names(scope: str = "full") -> set[str]:
    server = create_mcp_server(scope=scope)
    return {tool.name for tool in server._tool_manager.list_tools()}


def _sse_result(payload: Any) -> httpx.Response:
    body = json.dumps({"jsonrpc": "2.0", "id": 1, "result": {"structuredContent": payload}})
    return httpx.Response(
        200, text=f"data: {body}\n\n", headers={"content-type": "text/event-stream"}
    )


def _search_handler(request: httpx.Request) -> httpx.Response:
    assert request.url.host == "mcp.luxalgo.com"
    assert request.url.path == "/mcp"
    body = json.loads(request.content.decode())
    assert body["method"] == "tools/call"
    assert body["params"]["name"] == "library_search"
    arguments = body["params"]["arguments"]
    # The required upstream `context` is injected server-side, never caller PII.
    assert arguments["context"] == LUXALGO_CONTEXT
    assert arguments["query"] == "rsi"
    return _sse_result(SEARCH_RESULT)


def _concept_handler(request: httpx.Request) -> httpx.Response:
    body = json.loads(request.content.decode())
    assert body["params"]["name"] == "library_get_concept"
    assert body["params"]["arguments"]["context"] == LUXALGO_CONTEXT
    assert body["params"]["arguments"]["slug"] == "rsi"
    return _sse_result(CONCEPT_RESULT)


def _fail_handler(request: httpx.Request) -> httpx.Response:
    raise AssertionError(f"no request expected, got {request.url}")


def _client(handler: Any) -> LuxAlgoClient:
    return LuxAlgoClient(transport=httpx.MockTransport(handler))


# ── registration ──────────────────────────────────────────────────────────


def test_all_eight_tools_registered_in_full_scope() -> None:
    assert LUXALGO_TOOL_NAMES <= _names("full")


def test_all_eight_tools_registered_in_read_scope() -> None:
    assert LUXALGO_TOOL_NAMES <= _names("read")
    assert LUXALGO_TOOL_NAMES <= READ_SCOPE_TOOLS


def test_tools_carry_free_entitlement_and_note() -> None:
    for name in LUXALGO_TOOL_NAMES:
        fn = _mcp(name)
        assert fn.entitlement == "free"
        assert "Entitlement: free" in (fn.__doc__ or "")
        assert "source code is not" in (fn.__doc__ or "")


# ── manifest / in-process parity ──────────────────────────────────────────


def test_tool_entitlements_declare_all_eight_as_free() -> None:
    assert set(TOOL_ENTITLEMENTS) == LUXALGO_TOOL_NAMES
    assert set(TOOL_ENTITLEMENTS.values()) == {"free"}


def test_manifest_carries_entitlement_key_and_note() -> None:
    manifest = {tool["function"]["name"]: tool for tool in build_orchestrator_tool_manifest()}
    for name in LUXALGO_TOOL_NAMES:
        entry = manifest[name]
        assert entry["entitlement"] == "free"
        assert "Entitlement: free" in entry["function"]["description"]


def test_generated_schemas_match_manifest_order() -> None:
    manifest_names = [
        tool["function"]["name"]
        for tool in build_orchestrator_tool_manifest()
        if tool["function"]["name"] in TOOL_ENTITLEMENTS
    ]
    assert [tool["function"]["name"] for tool in LUXALGO_TOOLS] == manifest_names
    assert set(RESEARCH_TOOLS) == LUXALGO_TOOL_NAMES


def test_available_tools_gated_by_kill_switch(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    assert len(available_luxalgo_tools()) == 8
    assert len(available_luxalgo_tools(RESEARCH_TOOLS)) == 8
    monkeypatch.setenv(LUXALGO_ENABLED_ENV, "0")
    assert available_luxalgo_tools() == []
    monkeypatch.delenv(LUXALGO_ENABLED_ENV)
    with pytest.raises(KeyError):
        available_luxalgo_tools(("luxalgo_library_search", "bogus_tool"))


def test_luxalgo_enabled_parsing() -> None:
    assert luxalgo_enabled(raw="") is True
    assert luxalgo_enabled(raw="1") is True
    assert luxalgo_enabled(raw="TRUE") is True
    assert luxalgo_enabled(raw="0") is False
    assert luxalgo_enabled(raw="false") is False
    assert luxalgo_enabled(raw="typo") is False


# ── dry call paths ────────────────────────────────────────────────────────


def test_mcp_search_dry_call_is_attributed(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(mcp_server, "_build_luxalgo_client", lambda: _client(_search_handler))
    payload = json.loads(_mcp("luxalgo_library_search")("rsi", 2))
    assert payload["source"] == "luxalgo"
    assert payload["provider_id"] == "luxalgo-hosted-mcp"
    assert payload["data"] == SEARCH_RESULT
    assert payload["attribution"] == LUXALGO_ATTRIBUTION
    # Search rows each carry their own url; with no single canonical page the
    # envelope falls back to the Library home.
    assert payload["source_url"] == LUXALGO_LIBRARY_URL
    assert payload["data"]["results"][0]["md_url"] == "https://luxalgo.com/library/rsi.md"


def test_mcp_concept_dry_call_links_canonical_url(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(mcp_server, "_build_luxalgo_client", lambda: _client(_concept_handler))
    payload = json.loads(_mcp("luxalgo_library_get_concept")("rsi"))
    assert payload["data"]["slug"] == "rsi"
    assert payload["data"]["content_markdown"].startswith("# RSI")
    assert payload["source_url"] == "https://luxalgo.com/library/rsi/"


def test_mcp_invalid_args_answer_invalid_input_with_no_request(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(mcp_server, "_build_luxalgo_client", lambda: _client(_fail_handler))
    payload = json.loads(_mcp("luxalgo_library_search")("", 10))
    assert payload["data"]["code"] == "invalid_input"
    assert payload["data"]["retryable"] is False


def test_dispatcher_dry_call_ok(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    dispatch = build_luxalgo_tool_dispatcher(_client(_concept_handler))
    result = dispatch("luxalgo_library_get_concept", {"slug": "rsi"})
    assert result["ok"] is True
    payload = json.loads(result["content"])
    assert payload["attribution"] == LUXALGO_ATTRIBUTION
    assert payload["data"]["slug"] == "rsi"


def test_dispatcher_invalid_args_no_request() -> None:
    dispatch = build_luxalgo_tool_dispatcher(_client(_fail_handler))
    result = dispatch("luxalgo_library_search", {"query": "", "limit": 10})
    assert result["ok"] is False
    assert json.loads(result["content"])["data"]["code"] == "invalid_input"


def test_dispatcher_unknown_tool() -> None:
    result = build_luxalgo_tool_dispatcher(_client(_fail_handler))("luxalgo_nope", {})
    assert result["ok"] is False
    assert "unknown luxalgo tool" in result["content"]


def test_kill_switch_disables_with_no_request(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setenv(LUXALGO_ENABLED_ENV, "off")
    client = LuxAlgoClient(transport=httpx.MockTransport(_fail_handler))
    envelope = client.library_search({"query": "rsi"})
    assert envelope.data.code == "upstream_error"
    assert "kill switch" in envelope.data.message
    result = build_luxalgo_tool_dispatcher()("luxalgo_library_search", {"query": "rsi"})
    assert result["ok"] is False
    assert "kill switch" in result["content"]


def test_orchestrator_invoke_dry_call(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    client = _client(_search_handler)
    monkeypatch.setattr(agent_tools, "build_luxalgo_client", lambda: client)
    response = TestClient(app, headers=auth_headers()).post(
        "/v1/orchestrator_invoke",
        json={"tool": "luxalgo_library_search", "arguments": {"query": "rsi", "limit": 2}},
    )
    assert response.status_code == 200
    body = response.json()
    assert body["ok"] is True
    assert body["data"]["attribution"] == LUXALGO_ATTRIBUTION
    assert body["data"]["data"] == SEARCH_RESULT


# ── license-boundary absences ─────────────────────────────────────────────


def test_no_source_code_or_broker_or_oauth_tools(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    manifest_names = {tool["function"]["name"] for tool in build_orchestrator_tool_manifest()}
    assert not (FORBIDDEN_UPSTREAM & manifest_names)
    assert not (FORBIDDEN_UPSTREAM & READ_SCOPE_TOOLS)
    assert not (FORBIDDEN_UPSTREAM & _names("full"))
    assert LUXALGO_MCP_URL == "https://mcp.luxalgo.com/mcp"
    # The Library home is the attribution fallback, never a caller-supplied URL.
    assert LUXALGO_LIBRARY_URL == "https://luxalgo.com/library/"
