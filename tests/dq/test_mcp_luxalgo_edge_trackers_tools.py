"""MCP wiring for the LuxAlgo Edge Stats + Trackers thin wrap (#4844).

Wrappers are exercised through FastMCP's tool manager with a
MockTransport-backed LuxAlgoClient patched over the env-seam builder. No
network, no key required (every wrapped tool is ``free``).

Unlike the Library tools (``structuredContent`` results), the edge/trackers
tools answer MCP content blocks whose text part is the JSON payload itself —
the dry calls below use that probe-verified shape.

Also pinned: the honesty disclaimer on every ``edge_report`` result, the
kill switch, server-side ``context`` injection, the upstream ``stale`` fold-in
for trackers payloads, and the boundary absences (``trackers_query``,
``library_get_source_code``, ``broker_*``/``journal_*``/``propfirms_*`` are
never wrapped).
"""

from __future__ import annotations

import json
from typing import Any

import httpx
import pytest

pytest.importorskip("mcp.server.fastmcp")

pytestmark = pytest.mark.unit

from digiquant.data.luxalgo import (  # noqa: E402
    LUXALGO_CONTEXT,
    LUXALGO_EDGE_ATTRIBUTION,
    LUXALGO_EDGE_URL,
    LUXALGO_ENABLED_ENV,
    LUXALGO_MCP_URL,
    LUXALGO_TRACKERS_ATTRIBUTION,
    LUXALGO_TRACKERS_URL,
    TOOL_ENTITLEMENTS,
    LuxAlgoClient,
    agent_tools,
    available_luxalgo_tools,
    build_luxalgo_tool_dispatcher,
)
from digiquant.mcp_server import READ_SCOPE_TOOLS, create_mcp_server  # noqa: E402
from digiquant.orchestrator_tools import build_orchestrator_tool_manifest  # noqa: E402
from digiquant.server import app  # noqa: E402
from digiquant.stats.honesty import DISCLAIMER  # noqa: E402
from fastapi.testclient import TestClient  # noqa: E402

from digiquant import mcp_server  # noqa: E402
from tests.digi_test_jwt import auth_headers  # noqa: E402

EDGE_TRACKERS_TOOL_NAMES = {
    "luxalgo_edge_symbols",
    "luxalgo_edge_presets",
    "luxalgo_edge_report",
    "luxalgo_trackers_datasets",
    "luxalgo_trackers_latest",
    "luxalgo_trackers_ticker",
}

#: Upstream tool names that must NEVER appear on the digiquant surface.
FORBIDDEN_UPSTREAM = {
    "luxalgo_trackers_query",
    "trackers_query",
    "luxalgo_library_get_source_code",
    "library_get_source_code",
    "luxalgo_broker_list",
    "luxalgo_journal_list",
    "luxalgo_propfirms_search",
    "luxalgo_edge_list",
}

SYMBOLS_RESULT = {
    "builtAt": "2026-09-30T04:02:05.033Z",
    "symbols": [
        {
            "symbol": "BTCUSDT",
            "assetClass": "crypto",
            "sessions": [{"sessionKey": "utc", "sessions": 2464}],
        }
    ],
    "note": "Derived session statistics only.",
}

PRESETS_RESULT = {
    "categories": ["gaps", "seasonality"],
    "presets": [
        {
            "id": "gap-fill",
            "title": "Gap Fill",
            "category": "gaps",
            "summary": "How often the gap fills.",
        }
    ],
}

REPORT_RESULT = {
    "preset": {"id": "gap-fill", "version": 1, "title": "Gap Fill"},
    "symbol": "BTCUSDT",
    "n": 1360,
    "successes": 1356,
    "estimate": 0.9971,
    "ci95": [0.9925, 0.9989],
    "guards": {"lowSample": False, "refused": False},
    "disclaimer": DISCLAIMER,
}

DATASETS_RESULT = {
    "license": "CC0-1.0",
    "repository": "https://github.com/LuxAlgo/market-trackers-data",
    "datasets": [
        {
            "id": "insider-transactions",
            "title": "Insider transactions",
            "rows": 17499,
            "stale": False,
            "tickerSearchable": True,
        }
    ],
}

LATEST_RESULT = {
    "dataset": "insider-transactions",
    "matched": 1413,
    "returned": 1,
    "rows": [{"id": "row-1", "ticker": "NVDA"}],
}

TICKER_RESULT = {
    "ticker": "NVDA",
    "year": 2026,
    "datasets": [{"id": "insider-transactions", "matches": 3, "rows": []}],
}


@pytest.fixture(autouse=True)
def clean_env(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.delenv(LUXALGO_ENABLED_ENV, raising=False)


def _mcp(name: str):
    return create_mcp_server()._tool_manager.get_tool(name).fn


def _names(scope: str = "full") -> set[str]:
    server = create_mcp_server(scope=scope)
    return {tool.name for tool in server._tool_manager.list_tools()}


def _content_block_result(payload: Any) -> httpx.Response:
    """Upstream content-block shape: result.content[0].text is the JSON payload."""
    body = json.dumps(
        {
            "jsonrpc": "2.0",
            "id": 1,
            "result": {"content": [{"type": "text", "text": json.dumps(payload)}]},
        }
    )
    return httpx.Response(
        200, text=f"data: {body}\n\n", headers={"content-type": "text/event-stream"}
    )


def _expect_call(upstream: str, extra: dict[str, Any] | None = None) -> Any:
    """A handler asserting endpoint, keylessness, context injection, and args."""

    def _handler(request: httpx.Request) -> httpx.Response:
        assert request.url.host == "mcp.luxalgo.com"
        assert request.url.path == "/mcp"
        assert "authorization" not in request.headers
        body = json.loads(request.content.decode())
        assert body["method"] == "tools/call"
        assert body["params"]["name"] == upstream
        arguments = body["params"]["arguments"]
        # The required upstream `context` is injected server-side, never caller PII.
        assert arguments.pop("context") == LUXALGO_CONTEXT
        for key, value in (extra or {}).items():
            assert arguments.get(key) == value
        payloads = {
            "edge_symbols": SYMBOLS_RESULT,
            "edge_presets": PRESETS_RESULT,
            "edge_report": REPORT_RESULT,
            "trackers_datasets": DATASETS_RESULT,
            "trackers_latest": LATEST_RESULT,
            "trackers_ticker": TICKER_RESULT,
        }
        return _content_block_result(payloads[upstream])

    return _handler


def _fail_handler(request: httpx.Request) -> httpx.Response:
    raise AssertionError(f"no request expected, got {request.url}")


def _client(handler: Any) -> LuxAlgoClient:
    return LuxAlgoClient(transport=httpx.MockTransport(handler))


# ── registration ──────────────────────────────────────────────────────────


def test_all_six_tools_registered_in_full_scope() -> None:
    assert EDGE_TRACKERS_TOOL_NAMES <= _names("full")


def test_all_six_tools_registered_in_read_scope() -> None:
    assert EDGE_TRACKERS_TOOL_NAMES <= _names("read")
    assert EDGE_TRACKERS_TOOL_NAMES <= READ_SCOPE_TOOLS


def test_tools_carry_free_entitlement_and_family_note() -> None:
    for name in EDGE_TRACKERS_TOOL_NAMES:
        fn = _mcp(name)
        assert fn.entitlement == "free"
        assert "Entitlement: free" in (fn.__doc__ or "")
        # Family notes, not the Library source-code note.
        assert "source code is not" not in (fn.__doc__ or "")
    for name in (
        "luxalgo_edge_symbols",
        "luxalgo_edge_presets",
        "luxalgo_edge_report",
    ):
        assert "historical frequencies" in (_mcp(name).__doc__ or "")
    for name in (
        "luxalgo_trackers_datasets",
        "luxalgo_trackers_latest",
        "luxalgo_trackers_ticker",
    ):
        assert "source of record" in (_mcp(name).__doc__ or "")


# ── manifest / in-process parity ──────────────────────────────────────────


def test_tool_entitlements_declare_all_six_as_free() -> None:
    assert EDGE_TRACKERS_TOOL_NAMES <= set(TOOL_ENTITLEMENTS)
    for name in EDGE_TRACKERS_TOOL_NAMES:
        assert TOOL_ENTITLEMENTS[name] == "free"


def test_manifest_carries_entitlement_key_and_family_note() -> None:
    manifest = {tool["function"]["name"]: tool for tool in build_orchestrator_tool_manifest()}
    for name in EDGE_TRACKERS_TOOL_NAMES:
        entry = manifest[name]
        assert entry["entitlement"] == "free"
        assert "Entitlement: free" in entry["function"]["description"]
        assert "source code is not" not in entry["function"]["description"]


def test_edge_report_manifest_quotes_disclaimer() -> None:
    manifest = {tool["function"]["name"]: tool for tool in build_orchestrator_tool_manifest()}
    assert DISCLAIMER in manifest["luxalgo_edge_report"]["function"]["description"]


def test_available_tools_gated_by_kill_switch(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    assert len(available_luxalgo_tools()) == 14
    monkeypatch.setenv(LUXALGO_ENABLED_ENV, "0")
    assert available_luxalgo_tools() == []


# ── dry call paths ────────────────────────────────────────────────────────


def test_mcp_edge_symbols_dry_call_is_attributed(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(
        mcp_server, "_build_luxalgo_client", lambda: _client(_expect_call("edge_symbols"))
    )
    payload = json.loads(_mcp("luxalgo_edge_symbols")())
    assert payload["data"] == SYMBOLS_RESULT
    assert payload["attribution"] == LUXALGO_EDGE_ATTRIBUTION
    assert payload["source_url"] == LUXALGO_EDGE_URL


def test_mcp_edge_report_dry_call_carries_disclaimer(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(
        mcp_server,
        "_build_luxalgo_client",
        lambda: _client(_expect_call("edge_report", {"preset": "gap-fill", "symbol": "BTCUSDT"})),
    )
    payload = json.loads(_mcp("luxalgo_edge_report")("gap-fill", "BTCUSDT"))
    assert payload["data"]["estimate"] == 0.9971
    assert payload["data"]["n"] == 1360
    # The disclaimer accompanies every rendered preset stat: upstream field
    # and envelope warnings both carry it.
    assert payload["data"]["disclaimer"] == DISCLAIMER
    assert DISCLAIMER in payload["warnings"]
    assert payload["attribution"] == LUXALGO_EDGE_ATTRIBUTION


def test_mcp_trackers_latest_dry_call_with_where_json(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(
        mcp_server,
        "_build_luxalgo_client",
        lambda: _client(_expect_call("trackers_latest", {"dataset": "insider-transactions"})),
    )
    payload = json.loads(
        _mcp("luxalgo_trackers_latest")(
            "insider-transactions", None, None, '{"code": "P"}', "newest", 10, 0
        )
    )
    assert payload["data"] == LATEST_RESULT
    assert payload["attribution"] == LUXALGO_TRACKERS_ATTRIBUTION
    assert payload["source_url"] == LUXALGO_TRACKERS_URL


def test_mcp_trackers_latest_bad_where_json_is_invalid_input(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(mcp_server, "_build_luxalgo_client", lambda: _client(_fail_handler))
    payload = json.loads(
        _mcp("luxalgo_trackers_latest")("insider-transactions", None, None, "nope")
    )
    assert payload["data"]["code"] == "invalid_input"
    payload = json.loads(_mcp("luxalgo_trackers_latest")("insider-transactions", None, None, "[1]"))
    assert payload["data"]["code"] == "invalid_input"


def test_mcp_trackers_ticker_dry_call(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(
        mcp_server,
        "_build_luxalgo_client",
        lambda: _client(_expect_call("trackers_ticker", {"ticker": "NVDA"})),
    )
    payload = json.loads(_mcp("luxalgo_trackers_ticker")("NVDA"))
    assert payload["data"]["ticker"] == "NVDA"
    assert payload["attribution"] == LUXALGO_TRACKERS_ATTRIBUTION


def test_mcp_trackers_datasets_dry_call(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(
        mcp_server,
        "_build_luxalgo_client",
        lambda: _client(_expect_call("trackers_datasets")),
    )
    payload = json.loads(_mcp("luxalgo_trackers_datasets")())
    assert payload["data"]["license"] == "CC0-1.0"


def test_mcp_invalid_args_answer_invalid_input_with_no_request(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(mcp_server, "_build_luxalgo_client", lambda: _client(_fail_handler))
    payload = json.loads(_mcp("luxalgo_edge_report")("", "BTCUSDT"))
    assert payload["data"]["code"] == "invalid_input"
    payload = json.loads(_mcp("luxalgo_trackers_latest")(""))
    assert payload["data"]["code"] == "invalid_input"
    payload = json.loads(_mcp("luxalgo_trackers_ticker")(""))
    assert payload["data"]["code"] == "invalid_input"
    payload = json.loads(_mcp("luxalgo_trackers_ticker")("NVDA", None, 99))
    assert payload["data"]["code"] == "invalid_input"


def test_trackers_stale_flag_folds_into_envelope() -> None:
    stale_payload = dict(DATASETS_RESULT, stale=True)
    client = _client(lambda request: _content_block_result(stale_payload))
    envelope = client.trackers_datasets({})
    assert envelope.stale is True
    assert envelope.data["stale"] is True


def test_dispatcher_dry_call_ok() -> None:
    dispatch = build_luxalgo_tool_dispatcher(
        _client(_expect_call("edge_report", {"preset": "gap-fill", "symbol": "BTCUSDT"}))
    )
    result = dispatch("luxalgo_edge_report", {"preset": "gap-fill", "symbol": "BTCUSDT"})
    assert result["ok"] is True
    payload = json.loads(result["content"])
    assert payload["attribution"] == LUXALGO_EDGE_ATTRIBUTION
    assert DISCLAIMER in payload["warnings"]


def test_dispatcher_trackers_ticker_ok() -> None:
    dispatch = build_luxalgo_tool_dispatcher(
        _client(_expect_call("trackers_ticker", {"ticker": "NVDA"}))
    )
    result = dispatch("luxalgo_trackers_ticker", {"ticker": "NVDA", "limit": 1})
    assert result["ok"] is True
    assert json.loads(result["content"])["attribution"] == LUXALGO_TRACKERS_ATTRIBUTION


def test_dispatcher_invalid_args_no_request() -> None:
    dispatch = build_luxalgo_tool_dispatcher(_client(_fail_handler))
    result = dispatch("luxalgo_edge_report", {"preset": "", "symbol": "BTCUSDT"})
    assert result["ok"] is False
    assert json.loads(result["content"])["data"]["code"] == "invalid_input"


def test_kill_switch_disables_with_no_request(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setenv(LUXALGO_ENABLED_ENV, "off")
    client = LuxAlgoClient(transport=httpx.MockTransport(_fail_handler))
    envelope = client.edge_report({"preset": "gap-fill", "symbol": "BTCUSDT"})
    assert envelope.data.code == "upstream_error"
    assert "kill switch" in envelope.data.message
    result = build_luxalgo_tool_dispatcher()("luxalgo_trackers_latest", {"dataset": "x"})
    assert result["ok"] is False
    assert "kill switch" in result["content"]


def test_orchestrator_invoke_dry_call(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    client = _client(_expect_call("edge_report", {"preset": "gap-fill", "symbol": "BTCUSDT"}))
    monkeypatch.setattr(agent_tools, "build_luxalgo_client", lambda: client)
    response = TestClient(app, headers=auth_headers()).post(
        "/v1/orchestrator_invoke",
        json={
            "tool": "luxalgo_edge_report",
            "arguments": {"preset": "gap-fill", "symbol": "BTCUSDT"},
        },
    )
    assert response.status_code == 200
    body = response.json()
    assert body["ok"] is True
    assert body["data"]["attribution"] == LUXALGO_EDGE_ATTRIBUTION
    assert body["data"]["data"] == REPORT_RESULT


# ── boundary absences ─────────────────────────────────────────────────────


def test_no_query_or_keyed_or_oauth_tools() -> None:
    manifest_names = {tool["function"]["name"] for tool in build_orchestrator_tool_manifest()}
    assert not (FORBIDDEN_UPSTREAM & manifest_names)
    assert not (FORBIDDEN_UPSTREAM & READ_SCOPE_TOOLS)
    assert not (FORBIDDEN_UPSTREAM & _names("full"))
    assert LUXALGO_MCP_URL == "https://mcp.luxalgo.com/mcp"
