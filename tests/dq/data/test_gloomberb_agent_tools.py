"""In-process digifetch_* tool surface for pipeline agents (#4146).

Offline: a ``httpx.MockTransport`` drives the real ``digifetch.HttpFetcher``
and the dispatcher is given the client directly (the same patchable seam the
MCP wrappers use). Covers schema/dispatcher parity with the orchestrator
manifest builders and the MCP wrappers, the curated per-phase subsets, the
runtime session + family kill-switch gates, the attribution envelope (including
the typed-error paths), and the client's cache/breaker locks.
"""

from __future__ import annotations

import inspect
import json
from concurrent.futures import ThreadPoolExecutor
from typing import Any, Literal, get_args, get_origin, get_type_hints

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
    SUBSTACK_SESSION_COOKIE_ENV,
    TOOL_ENTITLEMENTS,
    GloomberbClient,
    agent_tools,
    available_digifetch_tools,
    build_digifetch_tool_dispatcher,
)
from digiquant.data.gloomberb.models import DigifetchEnvelope  # noqa: E402
from digiquant.orchestrator_tools import build_orchestrator_tool_manifest  # noqa: E402
from digiquant.tool_names import canonical_tool_name  # noqa: E402
from digiquant.tool_refusals import REFUSED_TOOLS  # noqa: E402

from digifetch import HttpFetcher, RateLimiter, RetryPolicy  # noqa: E402

MANIFEST = {t["function"]["name"]: t for t in build_orchestrator_tool_manifest()}

#: Declared-entitlement names on Counsel's refusal list keep their declaration but
#: are advertised nowhere (DIG-1057), so every manifest-parity assertion below is
#: stated over the live names.
REFUSED_DIGIFETCH = {name for name in REFUSED_TOOLS if name.startswith("digifetch_")}
LIVE_ENTITLEMENTS = {n: v for n, v in TOOL_ENTITLEMENTS.items() if n not in REFUSED_DIGIFETCH}

#: Entitlements whose tools were retired with the session-cookie path (DIG-3907).
#: The server keeps the same set as a function-local of ``create_mcp_server``
#: (``digiquant/src/digiquant/mcp_server.py:692``), so it cannot be imported
#: here; a drift in either direction fails the wrapper test below, which
#: expects a retired-entitlement row to be unregistered and a live row to be
#: registered.
RETIRED_ENTITLEMENTS = {"session", "preview", "pro"}

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
    kwargs.setdefault("enabled", True)
    return GloomberbClient(fetcher=fetcher, **kwargs)


def _envelope(data: Any, status: str = "success", **extra: Any) -> httpx.Response:
    return httpx.Response(200, json={"status": status, "data": data, **extra})


def _content(result: str | dict[str, Any]) -> str:
    """Unwrap the #4556 dispatcher result: ``{"content": <json str>, "ok": bool}``."""
    if isinstance(result, str):
        return result
    return str(result["content"])


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
    # A refused tool keeps its declaration but is advertised nowhere (DIG-1057),
    # so the manifest is the live names.
    assert set(LIVE_ENTITLEMENTS) == manifest_digifetch
    assert set(names) == manifest_digifetch
    assert REFUSED_DIGIFETCH <= set(TOOL_ENTITLEMENTS)
    assert not REFUSED_DIGIFETCH & manifest_digifetch
    for tool in DIGIFETCH_TOOLS:
        assert tool == MANIFEST[tool["function"]["name"]]


def test_dispatch_table_covers_every_schema_and_matches_its_parameters() -> None:
    # The dispatch table keeps its refused rows on purpose (the client code stays
    # in-tree for a possible Counsel clearance), so parity is stated over the
    # live names and the refused rows are checked separately below.
    assert set(DIGIFETCH_DISPATCH) - REFUSED_DIGIFETCH == {
        t["function"]["name"] for t in DIGIFETCH_TOOLS
    }
    for name, spec in DIGIFETCH_DISPATCH.items():
        if name in REFUSED_DIGIFETCH:
            continue
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


class _StubGloomberbClient:
    """Client stub: every method answers with an empty digifetch envelope."""

    def __getattr__(self, name: str) -> Any:
        def _call(request: Any = None) -> Any:
            return DigifetchEnvelope(data={"echo": "stub"})

        return _call


def _sentinel(param_name: str) -> str:
    """A recognisable stand-in value for one wrapper parameter."""
    return "SNT" + param_name.replace("_", "").upper()


def _argument_value(param_name: str, annotation: Any) -> Any:
    """A harmless value for one wrapper parameter, picked from its annotation."""
    origin = get_origin(annotation)
    if origin is Literal:
        return get_args(annotation)[0]
    if origin in (list, tuple, set):
        args = get_args(annotation)
        return [_argument_value(param_name, args[0] if args else str)]
    if origin is dict:
        return {}
    if annotation is int:
        return 1
    if annotation is float:
        return 1.0
    if annotation is bool:
        return True
    if annotation is str and "json" in param_name.lower():
        # ``digifetch_custom_chart``/``digifetch_options_scenario`` parse this.
        return "[]"
    return _sentinel(param_name)


def _wrapper_arguments(wrapper: Any) -> dict[str, Any]:
    """Every parameter of one MCP wrapper, each carrying a harmless value."""
    try:
        hints = get_type_hints(wrapper)
    except Exception:  # pragma: no cover - unresolvable forward reference
        hints = {}
    return {
        name: _argument_value(name, hints.get(name, str))
        for name in inspect.signature(wrapper).parameters
    }


def test_dispatch_link_and_attribution_match_the_mcp_wrappers(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """The live MCP wrappers honour their dispatch row's §7 envelope choices.

    Behavioural, not a source scrape: every live ``digifetch_*`` tool the MCP
    server registers is called against a stub client, and the envelope it
    returns must carry the attribution block exactly when the row says
    ``attributed`` and a deep link exactly when the row names a symbol field
    (#4146 review F4). A wrapper that changes its choice fails here.

    The lane that runs this file installs ``--extra mcp``, so a missing mcp is
    a broken lane, not a reason to skip the §7 contract.
    """
    try:
        import mcp.server.fastmcp  # noqa: F401
    except ImportError:
        pytest.fail(
            "mcp is not installed: the digiquant lane must sync `--extra mcp` "
            "(see .github/workflows/test-digiquant.yml), otherwise the §7 "
            "envelope contract is not gated in CI"
        )
    from digiquant import mcp_server

    monkeypatch.setattr(mcp_server, "_build_gloomberb_client", lambda: _StubGloomberbClient())
    manager = mcp_server.create_mcp_server(scope="full")._tool_manager
    for name, spec in sorted(DIGIFETCH_DISPATCH.items()):
        tool = manager.get_tool(canonical_tool_name(name))
        if TOOL_ENTITLEMENTS.get(name) in RETIRED_ENTITLEMENTS or name in REFUSED_DIGIFETCH:
            assert tool is None, name
            continue
        assert tool is not None, name
        payload = json.loads(tool.fn(**_wrapper_arguments(tool.fn)))
        assert "error" not in payload, f"{name}: {payload}"
        assert ("attribution" in payload) is spec.attributed, name
        assert ("delay_notice" in payload) is spec.attributed, name
        if spec.attributed:
            assert payload["attribution"] == GLOOMBERB_ATTRIBUTION, f"{name}: {payload}"
            assert payload["delay_notice"] == GLOOMBERB_DELAY_NOTICE, f"{name}: {payload}"
        assert ("source_url" in payload) is (spec.symbol_field is not None), name
        if spec.symbol_field is not None:
            assert _sentinel(spec.symbol_field) in payload["source_url"], f"{name}: {payload}"
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
def test_available_digifetch_tools_drops_exactly_the_retired_names(
    subset: tuple[str, ...], monkeypatch: pytest.MonkeyPatch
) -> None:
    # Enable the family first (default is OFF in deployed environments).
    # DIG-3907: the cookie path is retired, so session/preview/pro names drop
    # with or without a cookie set — the cookie no longer opens anything.
    monkeypatch.setenv(GLOOMBERB_ENABLED_ENV, "1")
    without_cookie = [t["function"]["name"] for t in available_digifetch_tools(subset)]
    monkeypatch.setenv(GLOOMBERB_SESSION_COOKIE_ENV, "gloomberb.session_token=test")
    with_cookie = [t["function"]["name"] for t in available_digifetch_tools(subset)]
    assert with_cookie == without_cookie
    assert with_cookie == [n for n in subset if TOOL_ENTITLEMENTS[n] == "free"]
    assert with_cookie  # each subset keeps its free core


def test_available_digifetch_tools_defaults_to_every_schema(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    # Enable the family first (default is OFF).
    monkeypatch.setenv(GLOOMBERB_ENABLED_ENV, "1")
    # No cookie → every free tool, in manifest order. Refused names keep their
    # entitlement declaration but are never advertised (DIG-1057).
    free = [n for n, v in LIVE_ENTITLEMENTS.items() if v == "free"]
    assert [t["function"]["name"] for t in available_digifetch_tools()] == free
    assert not REFUSED_DIGIFETCH & set(free)
    # DIG-3907: a cookie no longer opens the retired session/preview/pro tools.
    monkeypatch.setenv(GLOOMBERB_SESSION_COOKIE_ENV, "token")
    assert [t["function"]["name"] for t in available_digifetch_tools()] == free
    # The venue_session reader needs its own venue cookie, not the Gloomberb one.
    assert len(available_digifetch_tools()) == len(free)
    monkeypatch.setenv(SUBSTACK_SESSION_COOKIE_ENV, "substack.sid=test")
    assert len(available_digifetch_tools()) == len(free) + 1


def test_pro_tool_is_never_advertised(monkeypatch: pytest.MonkeyPatch) -> None:
    # Enable the family first (default is OFF in deployed environments).
    # DIG-3907: the cookie path is retired, so a pro tool stays dropped with
    # or without a cookie set.
    monkeypatch.setenv(GLOOMBERB_ENABLED_ENV, "1")
    assert available_digifetch_tools(("digifetch_transcripts",)) == []
    monkeypatch.setenv(GLOOMBERB_SESSION_COOKIE_ENV, "token")
    assert available_digifetch_tools(("digifetch_transcripts",)) == []


def test_available_digifetch_tools_rejects_an_unknown_name(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    # Enable the family first (default is OFF in deployed environments).
    monkeypatch.setenv(GLOOMBERB_ENABLED_ENV, "1")
    with pytest.raises(KeyError):
        available_digifetch_tools(("digifetch_not_a_tool",))


def test_keyless_tools_are_advertised_by_default_without_any_credential(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """DIG-2752 rescope (Chris, decision d4922299): the keyless surface is ON by default.

    Supersedes the DIG-1233 opt-in: a deployment with no ``GLOOMBERB_ENABLED``
    and no cookie must be handed exactly the ``free`` tools, and nothing that
    needs a credential. The gated tools stay hidden because the session gate
    answers ``no_secret`` before it makes any request.
    """
    monkeypatch.delenv(GLOOMBERB_ENABLED_ENV, raising=False)
    monkeypatch.delenv(GLOOMBERB_SESSION_COOKIE_ENV, raising=False)
    monkeypatch.delenv(SUBSTACK_SESSION_COOKIE_ENV, raising=False)

    # Anchor on the ADVERTISABLE set (the schemas), not on every entitlement:
    # the entitlement table carries at least one name with no schema, so an
    # entitlement-wide expectation would be unsatisfiable by construction.
    schema_names = {t["function"]["name"] for t in DIGIFETCH_TOOLS}
    expected = {n for n in schema_names if TOOL_ENTITLEMENTS[n] == "free"}
    gated = {n for n in schema_names if TOOL_ENTITLEMENTS[n] != "free"}
    # Non-vacuity: both halves must be non-empty or the equality below is vacuous.
    # Non-vacuity: both halves must be non-empty or the equality proves nothing.
    assert expected, "no free tools: the equality below would hold vacuously"
    assert gated, "no gated tools: the exclusion below would hold vacuously"

    advertised = {t["function"]["name"] for t in available_digifetch_tools()}
    assert advertised == expected
    assert advertised.isdisjoint(gated)


def test_explicit_disable_withholds_the_keyless_subset(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """``GLOOMBERB_ENABLED=0`` stays a full-family stop, and a typo still fails closed.

    The default flipped ON, so the opt-OUT is the property that now carries the
    safety burden; it must be pinned in both its explicit and its typo form.
    """
    monkeypatch.delenv(GLOOMBERB_SESSION_COOKIE_ENV, raising=False)

    monkeypatch.setenv(GLOOMBERB_ENABLED_ENV, "0")
    assert available_digifetch_tools() == []

    monkeypatch.setenv(GLOOMBERB_ENABLED_ENV, "ture")
    assert available_digifetch_tools() == []


def test_available_digifetch_tools_honours_an_explicit_opt_in_and_opt_out(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """The default moved (DIG-2752 rescope), so these two arms are what is left.

    An explicit ``GLOOMBERB_ENABLED=1`` must still enable the family for a
    deployment that sets it, and ``=0`` must still stop it for *every* subset.
    The unset-by-default behaviour is pinned by
    ``test_keyless_tools_are_advertised_by_default_without_any_credential`` and
    the ``=0``/typo stop by ``test_explicit_disable_withholds_the_keyless_subset``.
    """
    monkeypatch.setenv(GLOOMBERB_ENABLED_ENV, "1")
    assert available_digifetch_tools()
    assert available_digifetch_tools(EQUITY_TOOLS)

    monkeypatch.setenv(GLOOMBERB_ENABLED_ENV, "0")
    assert available_digifetch_tools() == []
    assert available_digifetch_tools(EQUITY_TOOLS) == []


# ── dispatcher routing + envelope ─────────────────────────────────────────────


def test_dispatcher_routes_and_returns_the_attributed_envelope() -> None:
    execute = build_digifetch_tool_dispatcher(client=make_client(_sweep_handler))
    payload = json.loads(_content(execute("digifetch_quote", {"symbol": "AAPL"})))
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
    payload = json.loads(_content(execute("digifetch_quote", {"symbol": "AAPL"})))
    assert payload["data"]["quote"]["price"] == 200.0


def test_dispatcher_uses_the_ticker_field_for_the_deep_link() -> None:
    execute = build_digifetch_tool_dispatcher(client=make_client(_sweep_handler))
    news = json.loads(_content(execute("digifetch_news", {"ticker": "AAPL"})))
    assert news["source_url"] == "https://term.gloom.sh/?ticker=AAPL"
    filings = json.loads(_content(execute("digifetch_sec_filings", {"ticker": "AAPL"})))
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
        _content(
            execute(
                "digifetch_price_history",
                {"symbol": "AAPL", "resolution": "1wk", "start_date": "2015-01-01"},
            )
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
    payload = json.loads(_content(execute("digifetch_earnings_calendar", {"symbols": ["AAPL"]})))
    assert "data" in payload
    assert "attribution" not in payload
    assert "source_url" not in payload


def test_dispatcher_maps_invalid_args_to_a_typed_error_without_a_request() -> None:
    def _fail(request: httpx.Request) -> httpx.Response:
        raise AssertionError("invalid input must not reach the wire")

    execute = build_digifetch_tool_dispatcher(client=make_client(_fail))
    # resolution is required for price_history — the Pydantic model rejects it.
    payload = json.loads(_content(execute("digifetch_price_history", {"symbol": "AAPL"})))
    assert payload["data"]["code"] == "invalid_input"
    assert payload["data"]["retryable"] is False
    # The raw payload still supplies the deep link the MCP wrapper emits (#4146
    # review F3).
    assert payload["source_url"] == "https://term.gloom.sh/?ticker=AAPL"


def test_dispatcher_non_mapping_args_return_typed_invalid_input() -> None:
    def _fail(request: httpx.Request) -> httpx.Response:
        raise AssertionError("non-mapping args must not reach the wire")

    execute = build_digifetch_tool_dispatcher(client=make_client(_fail))
    payload = json.loads(_content(execute("digifetch_quote", ["AAPL"])))  # type: ignore[arg-type]
    assert payload["data"]["code"] == "invalid_input"
    assert payload["data"]["retryable"] is False
    assert payload["attribution"] == GLOOMBERB_ATTRIBUTION


def test_retired_session_tool_without_a_cookie_is_auth_required_without_a_request() -> None:
    def _fail(request: httpx.Request) -> httpx.Response:
        raise AssertionError("a missing cookie must gate before any request")

    execute = build_digifetch_tool_dispatcher(client=make_client(_fail))
    payload = json.loads(_content(execute("digifetch_holders", {"symbol": "AAPL"})))
    assert payload["data"]["code"] == "auth_required"
    # The MCP wrapper deep-links even the typed error; the dispatcher matches.
    assert payload["source_url"] == "https://term.gloom.sh/?ticker=AAPL"


def test_dispatcher_never_raises_on_a_client_fault() -> None:
    class _Boom:
        def quote(self, request: Any) -> Any:
            raise RuntimeError("nope")

    result = build_digifetch_tool_dispatcher(client=_Boom())("digifetch_quote", {})
    assert isinstance(result, dict)
    # #4556: the dispatcher never raises, but it must not claim success either.
    assert result["ok"] is False
    assert "RuntimeError" in json.loads(_content(result))["error"]


def test_dispatcher_reports_unknown_tool_names() -> None:
    result = build_digifetch_tool_dispatcher(client=make_client(_sweep_handler))("nope", {})
    assert isinstance(result, dict)
    assert result["ok"] is False
    assert _content(result).startswith("Error: unknown digifetch tool")


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


def test_dispatcher_success_reports_ok_true() -> None:
    execute = build_digifetch_tool_dispatcher(client=make_client(_sweep_handler))

    result = execute("digifetch_quote", {"symbol": "AAPL"})

    assert isinstance(result, dict)
    assert result["ok"] is True
    assert json.loads(_content(result))["data"]["quote"]["price"] == 200.0


def test_dispatcher_upstream_fault_reports_ok_false() -> None:
    # A live-read 5xx that survives the client's own retries is a *failed* tool
    # call and must not be recorded as success (#4556).
    def _boom(request: httpx.Request) -> httpx.Response:
        raise RuntimeError("gloom upstream exploded")

    execute = build_digifetch_tool_dispatcher(client=make_client(_boom))

    result = execute("digifetch_quote", {"symbol": "AAPL"})

    assert isinstance(result, dict)
    assert result["ok"] is False
    assert "RuntimeError" in json.loads(_content(result))["error"]
