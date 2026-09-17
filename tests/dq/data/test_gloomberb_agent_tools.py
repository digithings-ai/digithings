"""In-process digifetch_* tool surface for pipeline agents (#4146).

Offline: a ``httpx.MockTransport`` drives the real ``digifetch.HttpFetcher``
and the dispatcher is given the client directly (the same patchable seam the
MCP wrappers use). Covers schema/dispatcher parity with the orchestrator
manifest builders and the MCP wrappers, the curated per-phase subsets, the
runtime session + family kill-switch gates, the attribution envelope (including
the typed-error paths), and the client's cache/breaker locks.
"""

from __future__ import annotations

import json
import re
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path
from typing import Any, get_args, get_type_hints

import httpx
import pytest
from pydantic import BaseModel

pytestmark = pytest.mark.unit

from digiquant.data.gloomberb import (  # noqa: E402
    DIGIFETCH_DISPATCH,
    DIGIFETCH_TOOLS,
    EQUITY_TOOLS,
    GLOOMBERB_ATTRIBUTION,
    GLOOMBERB_DELAY_NOTICE,
    GLOOMBERB_ENABLED_ENV,
    GLOOMBERB_SESSION_COOKIE_ENV,
    MACRO_TOOLS,
    PM_TOOLS,
    TOOL_ENTITLEMENTS,
    GloomberbClient,
    agent_tools,
    available_digifetch_tools,
    build_digifetch_tool_dispatcher,
)
from digiquant.orchestrator_tools import build_orchestrator_tool_manifest  # noqa: E402

from digifetch import HttpFetcher, RateLimiter, RetryPolicy  # noqa: E402

MANIFEST = {t["function"]["name"]: t for t in build_orchestrator_tool_manifest()}

_REPO_ROOT = Path(__file__).resolve().parents[3]

AAPL_QUOTE = {
    "symbol": "AAPL",
    "currency": "USD",
    "price": 200.0,
    "change": 1.0,
    "changePercent": 0.5,
    "lastUpdated": 1773000000000,
    "marketState": "CLOSED",
    "listingExchangeName": "NASDAQ",
    "dataSource": "delayed",
}


@pytest.fixture(autouse=True)
def clean_env(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.delenv(GLOOMBERB_ENABLED_ENV, raising=False)
    monkeypatch.delenv(GLOOMBERB_SESSION_COOKIE_ENV, raising=False)


def make_client(handler: Any, **kwargs: Any) -> GloomberbClient:
    fetcher = HttpFetcher(
        transport=httpx.MockTransport(handler),
        allowed_hosts=["api.gloom.sh"],
    )
    kwargs.setdefault("rate_limiter", RateLimiter(0))
    kwargs.setdefault("retry_policy", RetryPolicy(attempts=1))
    return GloomberbClient(fetcher=fetcher, **kwargs)


def _envelope(data: Any, status: str = "success", **extra: Any) -> httpx.Response:
    return httpx.Response(200, json={"status": status, "data": data, **extra})


def _sweep_handler(request: httpx.Request) -> httpx.Response:
    path = request.url.path
    if path == "/market/quote":
        return _envelope(AAPL_QUOTE)
    if path == "/market/holders":
        return _envelope({"symbol": "AAPL", "holders": []})
    if path == "/news":
        return httpx.Response(
            200, json={"items": [{"id": "n1", "headline": "Headline"}], "nextCursor": None}
        )
    if path == "/cloud/sec/filings":
        return httpx.Response(200, json={"filings": [], "hasMore": False, "nextOffset": 0})
    raise AssertionError(f"unexpected request: {request.url}")


# ── schema / dispatcher parity with the manifest builders ─────────────────────


def test_schemas_are_the_manifest_entries_for_the_entitled_names() -> None:
    names = [t["function"]["name"] for t in DIGIFETCH_TOOLS]
    assert names and len(names) == len(set(names))
    # Derived from the manifest surface, not round-tripped through the same
    # TOOL_ENTITLEMENTS filter: a builder added to the manifest without a
    # declaration fails here instead of being silently dropped from the
    # in-process surface (#4146 review F4).
    manifest_digifetch = {name for name in MANIFEST if name.startswith("digifetch_")}
    assert set(TOOL_ENTITLEMENTS) == manifest_digifetch
    assert set(names) == manifest_digifetch
    for tool in DIGIFETCH_TOOLS:
        assert tool == MANIFEST[tool["function"]["name"]]


def test_dispatch_table_covers_every_schema_and_matches_its_parameters() -> None:
    assert set(DIGIFETCH_DISPATCH) == {t["function"]["name"] for t in DIGIFETCH_TOOLS}
    for name, spec in DIGIFETCH_DISPATCH.items():
        params = MANIFEST[name]["function"]["parameters"]
        assert set(params.get("properties", {})) == set(spec.input_model.model_fields), name
        required = {f for f, v in spec.input_model.model_fields.items() if v.is_required()}
        assert set(params.get("required", [])) == required, name


def test_dispatch_rows_match_the_client_methods() -> None:
    for name, spec in DIGIFETCH_DISPATCH.items():
        method = getattr(GloomberbClient, spec.client_method, None)
        assert callable(method), f"{name}: GloomberbClient.{spec.client_method} missing"
        # The row's input model must be the first BaseModel in the method's
        # annotated request union (``Model | Mapping[str, Any]``).
        models = [
            arg
            for arg in get_args(get_type_hints(method)["request"])
            if isinstance(arg, type) and issubclass(arg, BaseModel)
        ]
        assert models == [spec.input_model], f"{name}: GloomberbClient.{spec.client_method}"


def _mcp_envelope_contract() -> dict[str, tuple[str | None, bool]]:
    """Parse the MCP wrappers' §7 envelope choices: ``name -> (symbol, attributed)``.

    Reads ``mcp_server.py`` instead of duplicating the contract as a hand table,
    so a wrapper that changes its deep-link/attribution choice fails this test
    until the dispatch row matches (#4146 review F4). Whitespace is flattened so
    a reformatted (wrapped) call still parses.
    """
    source = (_REPO_ROOT / "digiquant/src/digiquant/mcp_server.py").read_text()
    contract: dict[str, tuple[str | None, bool]] = {}
    for chunk in source.split('@_maybe_tool("')[1:]:
        name, _, body = chunk.partition('"')
        if not name.startswith("digifetch_"):
            continue
        flat = " ".join(body.split())
        call = re.search(r"_gloomberb_envelope_json\(([^)]*)\)", flat)
        assert call is not None, name
        args = call.group(1)
        symbol = re.search(r"symbol=(\w+)", args)
        contract[name] = (symbol.group(1) if symbol else None, "attributed=False" not in args)
    return contract


def test_dispatch_link_and_attribution_match_the_mcp_wrappers() -> None:
    contract = _mcp_envelope_contract()
    assert set(contract) == set(DIGIFETCH_DISPATCH)
    for name, spec in DIGIFETCH_DISPATCH.items():
        assert spec.symbol_field == contract[name][0], name
        assert spec.attributed is contract[name][1], name
        if spec.symbol_field is not None:
            assert spec.symbol_field in spec.input_model.model_fields, name


def test_subsets_are_real_distinct_and_prompt_budgeted() -> None:
    for subset in (EQUITY_TOOLS, MACRO_TOOLS, PM_TOOLS):
        assert 0 < len(subset) <= 16
        assert len(set(subset)) == len(subset)  # no duplicates
        assert set(subset) <= set(TOOL_ENTITLEMENTS)
    assert len({frozenset(EQUITY_TOOLS), frozenset(MACRO_TOOLS), frozenset(PM_TOOLS)}) == 3


# ── runtime session gate ──────────────────────────────────────────────────────


@pytest.mark.parametrize(
    "subset", [EQUITY_TOOLS, MACRO_TOOLS, PM_TOOLS], ids=["equity", "macro", "pm"]
)
def test_available_digifetch_tools_drops_exactly_the_gated_names(
    subset: tuple[str, ...], monkeypatch: pytest.MonkeyPatch
) -> None:
    without_cookie = [t["function"]["name"] for t in available_digifetch_tools(subset)]
    monkeypatch.setenv(GLOOMBERB_SESSION_COOKIE_ENV, "gloomberb.session_token=test")
    with_cookie = [t["function"]["name"] for t in available_digifetch_tools(subset)]
    assert with_cookie == list(subset)  # all subset names are free/session
    assert without_cookie == [n for n in with_cookie if TOOL_ENTITLEMENTS[n] == "free"]
    assert without_cookie  # each subset keeps its free core


def test_available_digifetch_tools_defaults_to_every_schema(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    # No cookie → every free tool, in manifest order.
    free = [n for n in TOOL_ENTITLEMENTS if TOOL_ENTITLEMENTS[n] == "free"]
    assert [t["function"]["name"] for t in available_digifetch_tools()] == free
    monkeypatch.setenv(GLOOMBERB_SESSION_COOKIE_ENV, "token")
    assert len(available_digifetch_tools()) == len(DIGIFETCH_TOOLS)


def test_pro_tool_gate_is_cookie_presence(monkeypatch: pytest.MonkeyPatch) -> None:
    assert available_digifetch_tools(("digifetch_transcripts",)) == []
    monkeypatch.setenv(GLOOMBERB_SESSION_COOKIE_ENV, "token")
    assert len(available_digifetch_tools(("digifetch_transcripts",))) == 1


def test_available_digifetch_tools_rejects_an_unknown_name() -> None:
    with pytest.raises(KeyError):
        available_digifetch_tools(("digifetch_not_a_tool",))


def test_available_digifetch_tools_respects_the_family_kill_switch(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    # Default ON (env unset) → schemas; disabled → never advertise a tool whose
    # every call can only return the typed disabled envelope (#4146 review F1).
    assert available_digifetch_tools()
    monkeypatch.setenv(GLOOMBERB_ENABLED_ENV, "0")
    assert available_digifetch_tools() == []
    assert available_digifetch_tools(EQUITY_TOOLS) == []
    # A typo fails closed, same as the client's kill switch.
    monkeypatch.setenv(GLOOMBERB_ENABLED_ENV, "ture")
    assert available_digifetch_tools() == []
    monkeypatch.setenv(GLOOMBERB_ENABLED_ENV, "1")
    assert available_digifetch_tools()


# ── dispatcher routing + envelope ─────────────────────────────────────────────


def test_dispatcher_routes_and_returns_the_attributed_envelope() -> None:
    execute = build_digifetch_tool_dispatcher(client=make_client(_sweep_handler))
    payload = json.loads(execute("digifetch_quote", {"symbol": "AAPL"}))
    assert payload["data"]["quote"]["price"] == 200.0
    assert payload["attribution"] == GLOOMBERB_ATTRIBUTION
    assert payload["delay_notice"] == GLOOMBERB_DELAY_NOTICE
    assert payload["source_url"] == "https://term.gloom.sh/?ticker=AAPL"


def test_dispatcher_defaults_to_the_shared_env_client(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    client = make_client(_sweep_handler)
    monkeypatch.setattr(agent_tools, "build_gloomberb_client", lambda: client)
    execute = build_digifetch_tool_dispatcher()
    payload = json.loads(execute("digifetch_quote", {"symbol": "AAPL"}))
    assert payload["data"]["quote"]["price"] == 200.0


def test_dispatcher_uses_the_ticker_field_for_the_deep_link() -> None:
    execute = build_digifetch_tool_dispatcher(client=make_client(_sweep_handler))
    news = json.loads(execute("digifetch_news", {"ticker": "AAPL"}))
    assert news["source_url"] == "https://term.gloom.sh/?ticker=AAPL"
    filings = json.loads(execute("digifetch_sec_filings", {"ticker": "AAPL"}))
    assert filings["source_url"] == "https://term.gloom.sh/?ticker=AAPL"


def test_dispatcher_routes_a_price_history_date_window() -> None:
    seen: dict[str, str] = {}

    def handler(request: httpx.Request) -> httpx.Response:
        seen["url"] = str(request.url)
        return _envelope(
            [{"date": "2015-01-05T00:00:00.000Z", "close": 100.0}],
            currency="USD",
            providerMeta={"provider": "yahoo"},
        )

    execute = build_digifetch_tool_dispatcher(client=make_client(handler))
    payload = json.loads(
        execute(
            "digifetch_price_history",
            {"symbol": "AAPL", "resolution": "1wk", "start_date": "2015-01-01"},
        )
    )
    assert "interval=1week" in seen["url"]
    assert "rangeKey=ALL" in seen["url"]
    assert "startDate=2015-01-01" in seen["url"]
    assert payload["data"]["bars"][0]["close"] == 100.0
    assert payload["source_url"] == "https://term.gloom.sh/?ticker=AAPL"
    assert payload["attribution"] == GLOOMBERB_ATTRIBUTION


def test_dispatcher_does_not_attribute_the_yahoo_earnings_calendar() -> None:
    client = make_client(_sweep_handler, earnings_provider=lambda symbol: [])
    execute = build_digifetch_tool_dispatcher(client=client)
    payload = json.loads(execute("digifetch_earnings_calendar", {"symbols": ["AAPL"]}))
    assert "data" in payload
    assert "attribution" not in payload
    assert "source_url" not in payload


def test_dispatcher_maps_invalid_args_to_a_typed_error_without_a_request() -> None:
    def _fail(request: httpx.Request) -> httpx.Response:
        raise AssertionError("invalid input must not reach the wire")

    execute = build_digifetch_tool_dispatcher(client=make_client(_fail))
    # resolution is required for price_history — the Pydantic model rejects it.
    payload = json.loads(execute("digifetch_price_history", {"symbol": "AAPL"}))
    assert payload["data"]["code"] == "invalid_input"
    assert payload["data"]["retryable"] is False
    # The raw payload still supplies the deep link the MCP wrapper emits (#4146
    # review F3).
    assert payload["source_url"] == "https://term.gloom.sh/?ticker=AAPL"


def test_dispatcher_non_mapping_args_return_typed_invalid_input() -> None:
    def _fail(request: httpx.Request) -> httpx.Response:
        raise AssertionError("non-mapping args must not reach the wire")

    execute = build_digifetch_tool_dispatcher(client=make_client(_fail))
    payload = json.loads(execute("digifetch_quote", ["AAPL"]))  # type: ignore[arg-type]
    assert payload["data"]["code"] == "invalid_input"
    assert payload["data"]["retryable"] is False
    assert payload["attribution"] == GLOOMBERB_ATTRIBUTION


def test_session_gated_tool_without_a_cookie_is_auth_required_without_a_request() -> None:
    def _fail(request: httpx.Request) -> httpx.Response:
        raise AssertionError("a missing cookie must gate before any request")

    execute = build_digifetch_tool_dispatcher(client=make_client(_fail))
    payload = json.loads(execute("digifetch_holders", {"symbol": "AAPL"}))
    assert payload["data"]["code"] == "auth_required"
    # The MCP wrapper deep-links even the typed error; the dispatcher matches.
    assert payload["source_url"] == "https://term.gloom.sh/?ticker=AAPL"


def test_dispatcher_never_raises_on_a_client_fault() -> None:
    class _Boom:
        def quote(self, request: Any) -> Any:
            raise RuntimeError("nope")

    payload = json.loads(build_digifetch_tool_dispatcher(client=_Boom())("digifetch_quote", {}))
    assert "RuntimeError" in payload["error"]


def test_dispatcher_reports_unknown_tool_names() -> None:
    result = build_digifetch_tool_dispatcher(client=make_client(_sweep_handler))("nope", {})
    assert result.startswith("Error: unknown digifetch tool")


# ── the shared client's parallel-node locks (#4146) ───────────────────────────


def test_client_breaker_counters_are_mutation_locked() -> None:
    client = make_client(_sweep_handler)
    threads = 32
    with ThreadPoolExecutor(max_workers=8) as pool:
        list(pool.map(lambda _i: client._record_failure(), range(threads)))
    assert client._consecutive_failures == threads


def test_client_cache_stays_bounded_under_parallel_reads() -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        symbol = request.url.params.get("symbol", "AAPL")
        return _envelope({**AAPL_QUOTE, "symbol": symbol})

    client = make_client(handler, cache_max_entries=4)
    with ThreadPoolExecutor(max_workers=8) as pool:
        list(pool.map(lambda i: client.quote({"symbol": f"S{i}"}), range(16)))
    assert client.cache_size <= 4
