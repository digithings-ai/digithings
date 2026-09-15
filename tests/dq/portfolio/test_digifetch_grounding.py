"""Portfolio grounding wires the PM digifetch subset — H5 + H7, not H6 (#4146)."""

from __future__ import annotations

import json
from datetime import date
from typing import Any

import httpx
import pytest
from digiquant.data.gloomberb import (
    GLOOMBERB_SESSION_COOKIE_ENV,
    PM_TOOLS,
    TOOL_ENTITLEMENTS,
    GloomberbClient,
    agent_tools,
)
from digiquant.portfolio.phases.h6_deliberation import _h6_grounding
from digiquant.portfolio.phases.portfolio_common import _portfolio_grounding
from digiquant.research.phases import _node_factory
from digiquant.research.state import ResearchConfigBundle, ResearchState

from digifetch import HttpFetcher, RateLimiter, RetryPolicy

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


def _state() -> ResearchState:
    return ResearchState(
        run_type="delta",
        run_date=date(2026, 9, 15),
        config=ResearchConfigBundle(watchlist=["AAPL"]),
    )


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
def _grounding_env(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("DIGIQUANT_RESEARCH_DATA_TOOLS", "1")
    monkeypatch.delenv(GLOOMBERB_SESSION_COOKIE_ENV, raising=False)
    monkeypatch.setattr(_node_factory, "_research_data_client", lambda: object())
    monkeypatch.setattr(
        "digiquant.research.data.web_grounding.fetch_web_grounding",
        lambda **_kwargs: {"summary": "canned", "sources": [], "as_of": "2026-09-15"},
    )


@pytest.mark.unit
@pytest.mark.parametrize("phase", ["h5_analyst", "h7_pm"])
def test_portfolio_grounding_equips_the_free_pm_subset(
    monkeypatch: pytest.MonkeyPatch, phase: str
) -> None:
    monkeypatch.setattr(agent_tools, "build_gloomberb_client", lambda: _client(_sweep_handler))
    tools, execute_tool, _ = _portfolio_grounding(_state(), phase=phase)
    assert tools is not None and execute_tool is not None
    names = {t["function"]["name"] for t in tools}
    free_pm = {n for n in PM_TOOLS if TOOL_ENTITLEMENTS[n] == "free"}
    gated_pm = {n for n in PM_TOOLS if TOOL_ENTITLEMENTS[n] != "free"}
    assert free_pm.issubset(names)
    # Session-gated names are absent without a cookie.
    assert names.isdisjoint(gated_pm)

    payload = json.loads(execute_tool("digifetch_quote", {"symbol": "AAPL"}))
    assert payload["data"]["quote"]["price"] == 200.0


@pytest.mark.unit
def test_h6_grounding_stays_digifetch_free() -> None:
    # Decision recorded in #4146: H6 is research-tools-only by policy (#2908);
    # its evidence path is the bundle + amendment flow, not a new data family.
    tools, _execute_tool, _ = _h6_grounding(_state())
    assert tools is not None
    assert not any(t["function"]["name"].startswith("digifetch_") for t in tools)
