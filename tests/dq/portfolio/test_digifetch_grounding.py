"""Portfolio grounding wires the PM digifetch subset — analyst + direction, not deliberation (#4146)."""

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
from digiquant.portfolio.phases import direction, portfolio_common
from digiquant.portfolio.phases.deliberation import _deliberation_grounding
from digiquant.portfolio.phases.portfolio_common import _portfolio_grounding
from digiquant.research.phases import _node_factory
from digiquant.research.state import (
    PhasePortfolioState,
    PriorContext,
    ResearchConfigBundle,
    ResearchState,
)

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
        baseline_date=date(2026, 9, 14),
        config=ResearchConfigBundle(watchlist=["AAPL"]),
        prior_context=PriorContext(),
        phase_portfolio=PhasePortfolioState(),
    )


def _raise(**_kwargs: Any) -> Any:
    """Short-circuit an LLM call after grounding has been recorded."""
    raise RuntimeError("stop after grounding")


def _record_grounding_calls(
    monkeypatch: pytest.MonkeyPatch, recorded: list[dict[str, Any]]
) -> None:
    """Spy on ``portfolio_common.build_grounding`` keeping the real behavior."""
    original = portfolio_common.build_grounding

    def spy(**kwargs: Any) -> Any:
        recorded.append(kwargs)
        return original(**kwargs)

    monkeypatch.setattr(portfolio_common, "build_grounding", spy)


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
@pytest.mark.parametrize("phase", ["analyst", "direction"])
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
def test_analyst_call_site_grounds_with_the_pm_subset(monkeypatch: pytest.MonkeyPatch) -> None:
    # Drive the real analyst entry point (not the helper directly) so dropping the
    # grounding call from the node path fails here (#4146 review F6).
    recorded: list[dict[str, Any]] = []
    _record_grounding_calls(monkeypatch, recorded)
    monkeypatch.setattr(agent_tools, "build_gloomberb_client", lambda: _client(_sweep_handler))
    monkeypatch.setattr(portfolio_common, "run_research_agent", _raise)

    payload, document, errors, _bundle = portfolio_common.run_asset_analyst_llm(
        state=_state(),
        ticker="AAPL",
        roster_entry={"ticker": "AAPL"},
        phase_slug="portfolio/asset-analyst-AAPL",
    )
    assert payload is None and document is None and errors
    assert recorded, "analyst must ground through portfolio_common.build_grounding"
    assert recorded[-1]["research_phase"] == "analyst"
    assert recorded[-1]["digifetch_tools"] == PM_TOOLS


@pytest.mark.unit
def test_direction_call_site_grounds_with_the_pm_subset(monkeypatch: pytest.MonkeyPatch) -> None:
    recorded: list[dict[str, Any]] = []
    _record_grounding_calls(monkeypatch, recorded)
    monkeypatch.setattr(agent_tools, "build_gloomberb_client", lambda: _client(_sweep_handler))
    monkeypatch.setattr(direction, "run_research_agent", _raise)

    out = direction._direction_node(_state())
    assert out.get("errors"), "the stubbed LLM failure must fail soft"
    assert recorded, "direction must ground through portfolio_common.build_grounding"
    assert recorded[-1]["research_phase"] == "direction"
    assert recorded[-1]["digifetch_tools"] == PM_TOOLS


@pytest.mark.unit
def test_deliberation_grounding_stays_digifetch_free() -> None:
    # Decision recorded in #4146: deliberation is research-tools-only by policy (#2908);
    # its evidence path is the bundle + amendment flow, not a new data family.
    tools, _execute_tool, _ = _deliberation_grounding(_state())
    assert tools is not None
    assert not any(t["function"]["name"].startswith("digifetch_") for t in tools)
