"""build_grounding wiring for the in-process digifetch family (#4146)."""

from __future__ import annotations

import json
from datetime import date
from typing import Any

import httpx
import pytest
from digiquant.data.gloomberb import (
    EQUITY_TOOLS,
    GLOOMBERB_ATTRIBUTION,
    GLOOMBERB_SESSION_COOKIE_ENV,
    GloomberbClient,
    agent_tools,
)
from digiquant.research.phases import _node_factory

from digifetch import HttpFetcher, RateLimiter, RetryPolicy


def _content(result: str | dict[str, Any]) -> str:
    """Unwrap a digifetch dispatcher result: ``{"content": <json str>, "ok": bool}`` (#4556)."""
    if isinstance(result, str):
        return result
    return str(result["content"])


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


def _client(handler: Any) -> GloomberbClient:
    fetcher = HttpFetcher(
        transport=httpx.MockTransport(handler),
        allowed_hosts=["api.gloom.sh"],
    )
    return GloomberbClient(
        fetcher=fetcher, rate_limiter=RateLimiter(0), retry_policy=RetryPolicy(attempts=1)
    )


def _sweep_handler(request: httpx.Request) -> httpx.Response:
    if request.url.path == "/market/quote":
        return httpx.Response(200, json={"status": "success", "data": AAPL_QUOTE})
    raise AssertionError(f"unexpected request: {request.url}")


@pytest.fixture(autouse=True)
def _clean_env(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("DIGIQUANT_RESEARCH_DATA_TOOLS", "1")
    monkeypatch.delenv(GLOOMBERB_SESSION_COOKIE_ENV, raising=False)
    monkeypatch.setattr(_node_factory, "_research_data_client", lambda: object())


@pytest.mark.unit
def test_build_grounding_omits_digifetch_by_default() -> None:
    tools, execute_tool, _ = _node_factory.build_grounding(
        use_data_tools=True, live_search=False, run_date=date(2026, 9, 15)
    )
    assert tools is not None and execute_tool is not None
    assert not any(t["function"]["name"].startswith("digifetch_") for t in tools)


@pytest.mark.unit
def test_build_grounding_adds_the_flagged_subset_and_routes_a_call(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(agent_tools, "build_gloomberb_client", lambda: _client(_sweep_handler))
    tools, execute_tool, _ = _node_factory.build_grounding(
        use_data_tools=True,
        live_search=False,
        run_date=date(2026, 9, 15),
        digifetch_tools=EQUITY_TOOLS,
    )
    assert tools is not None and execute_tool is not None
    names = {t["function"]["name"] for t in tools}
    assert "digifetch_quote" in names
    # Session-gated names drop out without GLOOMBERB_SESSION_COOKIE.
    assert "digifetch_analyst_research" not in names

    payload = json.loads(_content(execute_tool("digifetch_quote", {"symbol": "AAPL"})))
    assert payload["data"]["quote"]["price"] == 200.0
    assert payload["attribution"] == GLOOMBERB_ATTRIBUTION


@pytest.mark.unit
def test_build_grounding_adds_session_tools_with_a_cookie(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setenv(GLOOMBERB_SESSION_COOKIE_ENV, "gloomberb.session_token=test")
    monkeypatch.setattr(
        agent_tools,
        "build_gloomberb_client",
        lambda: _client(_sweep_handler),
    )
    tools, _execute_tool, _ = _node_factory.build_grounding(
        use_data_tools=True,
        live_search=False,
        run_date=date(2026, 9, 15),
        digifetch_tools=EQUITY_TOOLS,
    )
    assert tools is not None
    names = {t["function"]["name"] for t in tools}
    assert "digifetch_analyst_research" in names  # session-gated, cookie present


@pytest.mark.unit
def test_build_grounding_omits_digifetch_when_no_primary_executor_builds(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    # Enrichment-only rule: digifetch never arms a tool loop on its own. With
    # no primary grounding executor (Supabase client unavailable) the segment
    # degrades to tool-less exactly as before #4146.
    def _boom() -> object:
        raise RuntimeError("supabase not configured")

    monkeypatch.setattr(_node_factory, "_research_data_client", _boom)
    tools, execute_tool, _ = _node_factory.build_grounding(
        use_data_tools=True,
        live_search=False,
        run_date=date(2026, 9, 15),
        digifetch_tools=EQUITY_TOOLS,
    )
    assert tools is None and execute_tool is None


@pytest.mark.unit
def test_build_grounding_composes_data_and_digifetch_executors(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(agent_tools, "build_gloomberb_client", lambda: _client(_sweep_handler))
    tools, execute_tool, _ = _node_factory.build_grounding(
        use_data_tools=True,
        live_search=False,
        run_date=date(2026, 9, 15),
        digifetch_tools=EQUITY_TOOLS,
    )
    assert tools is not None and execute_tool is not None
    names = {t["function"]["name"] for t in tools}
    # query_data was retired in #4436; the typed macro reader is the data-family
    # marker that proves the data executor composed alongside digifetch.
    assert {"get_macro_series", "digifetch_quote"}.issubset(names)
    # The combined dispatcher routes by family and rejects unknown names.
    payload = json.loads(_content(execute_tool("digifetch_quote", {"symbol": "AAPL"})))
    assert payload["data"]["quote"]["price"] == 200.0
    assert _content(execute_tool("definitely_not_a_tool", {})).startswith("Error:")


@pytest.mark.unit
def test_build_grounding_kill_switch_disables_digifetch(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    # A working data client (autouse fixture) plus a working digifetch client, so
    # the env var is the only difference — the old version of this test passed
    # vacuously because use_data_tools=False left no executors to attach to
    # (#4146 review F5).
    monkeypatch.setattr(agent_tools, "build_gloomberb_client", lambda: _client(_sweep_handler))
    monkeypatch.setenv("DIGIQUANT_RESEARCH_DATA_TOOLS", "0")
    tools, _execute_tool, _ = _node_factory.build_grounding(
        use_data_tools=True,
        live_search=False,
        run_date=date(2026, 9, 15),
        digifetch_tools=EQUITY_TOOLS,
    )
    names = set() if tools is None else {t["function"]["name"] for t in tools}
    assert not any(name.startswith("digifetch_") for name in names)

    monkeypatch.setenv("DIGIQUANT_RESEARCH_DATA_TOOLS", "1")
    tools, _execute_tool, _ = _node_factory.build_grounding(
        use_data_tools=True,
        live_search=False,
        run_date=date(2026, 9, 15),
        digifetch_tools=EQUITY_TOOLS,
    )
    assert tools is not None
    assert "digifetch_quote" in {t["function"]["name"] for t in tools}
