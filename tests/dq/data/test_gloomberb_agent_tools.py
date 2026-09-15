"""In-process digifetch_* tool surface for pipeline agents (#4146).

Offline: a ``httpx.MockTransport`` drives the real ``digifetch.HttpFetcher``
and the dispatcher is given the client directly (the same patchable seam the
MCP wrappers use). Covers schema/dispatcher parity with the orchestrator
manifest builders, the curated per-phase subsets, the runtime session gate,
the attribution envelope, and the client's cache/breaker locks.
"""

from __future__ import annotations

import json
from concurrent.futures import ThreadPoolExecutor
from typing import Any

import httpx
import pytest

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
    assert set(names) == set(TOOL_ENTITLEMENTS)
    for tool in DIGIFETCH_TOOLS:
        assert tool == MANIFEST[tool["function"]["name"]]


def test_dispatch_table_covers_every_schema_and_matches_its_parameters() -> None:
    assert set(DIGIFETCH_DISPATCH) == {t["function"]["name"] for t in DIGIFETCH_TOOLS}
    for name, spec in DIGIFETCH_DISPATCH.items():
        params = MANIFEST[name]["function"]["parameters"]
        assert set(params.get("properties", {})) == set(spec.input_model.model_fields), name
        required = {f for f, v in spec.input_model.model_fields.items() if v.is_required()}
        assert set(params.get("required", [])) == required, name


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
