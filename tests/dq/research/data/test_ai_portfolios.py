"""Tool-only ai-portfolio grounding: the X leg succeeds or raises (#3859 Task 4).

No synthesis fallback, no vendor prefix gate: ``fetch_ai_portfolio_grounding``
reads the tracked accounts through the first-party ``web_search`` tool scoped
to x.com / twitter.com. Missing roster, empty results, and tool errors all
raise ``DashboardWebSearchError`` unconditionally.
"""

from __future__ import annotations

from datetime import date
from typing import Any

import pytest

pytest.importorskip("openai")

from digiquant.research.data import ai_portfolios
from digiquant.research.data.web_grounding import DashboardWebSearchError

# digisearch's WebSearchRequest.query is Field(max_length=500) (#3853). Kept as
# a literal so this test fails on the code that sent an over-long query, rather
# than erroring on a constant that only the fix introduces.
_DIGISEARCH_QUERY_CAP = 500


def _tool_ok(
    monkeypatch: pytest.MonkeyPatch,
    seen: dict[str, Any],
    summary: str = "@grkportfolio bought $GFI",
    sources: list[str] | None = None,
) -> None:
    def _fake(**kwargs: Any) -> dict[str, Any]:
        seen.update(kwargs)
        return {
            "summary": summary,
            "sources": list(sources) if sources is not None else ["https://x.com/s/1"],
        }

    monkeypatch.setattr(ai_portfolios, "call_web_search_tool", _fake)


@pytest.mark.unit
def test_fetch_ai_portfolio_grounding_returns_summary_sources_handles(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    seen: dict[str, Any] = {}
    _tool_ok(
        monkeypatch,
        seen,
        summary="@grkportfolio bought $GFI",
        sources=["https://x.com/grkportfolio/status/1"],
    )
    out = ai_portfolios.fetch_ai_portfolio_grounding(model="cheap", run_date=date(2026, 6, 9))
    assert "$GFI" in out["summary"]
    assert out["sources"] == ["https://x.com/grkportfolio/status/1"]
    assert out["as_of"] == "2026-06-09"
    assert out["accounts"]  # the tracked handles, for transparency
    # X-scoped tool call: x.com + twitter.com only, handles named in the query.
    assert seen["include_domains"] == ["x.com", "twitter.com"]
    for h in ("theaiportfolios", "grkportfolio", "ralliesarena", "geminiportfolio"):
        assert h in seen["query"]


@pytest.mark.unit
def test_the_query_fits_the_digisearch_request_cap(monkeypatch: pytest.MonkeyPatch) -> None:
    """digisearch caps ``query`` at 500 chars; over it the tool 400s and the
    whole book run fails (#4163)."""
    seen: dict[str, Any] = {}
    _tool_ok(monkeypatch, seen)
    ai_portfolios.fetch_ai_portfolio_grounding(model="cheap", run_date=date(2026, 6, 9))
    assert len(seen["query"]) <= _DIGISEARCH_QUERY_CAP


@pytest.mark.unit
def test_the_query_is_a_search_query_not_a_synthesis_prompt(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """digisearch's ``web_search`` returns result rows and the caller formats the
    summary (``web_grounding.call_web_search_tool``), so instruction text in the
    query only dilutes it (#4163)."""
    seen: dict[str, Any] = {}
    _tool_ok(monkeypatch, seen)
    ai_portfolios.fetch_ai_portfolio_grounding(model="cheap", run_date=date(2026, 6, 9))
    query = seen["query"]
    for handle in (
        "theaiportfolios",
        "grkportfolio",
        "ralliesarena",
        "aifinancelabs",
        "geminiportfolio",
        "theAIportfolio",
    ):
        assert f"@{handle}" in query
    assert "holdings" in query and "tickers" in query
    assert "For EACH account" not in query
    assert "CROSS-ACCOUNT" not in query


@pytest.mark.unit
def test_the_config_recency_days_reaches_the_tool_call(monkeypatch: pytest.MonkeyPatch) -> None:
    """``ai_portfolio_accounts.yaml``'s ``recency_days`` must reach the request; it
    used to sit dead while digisearch's own default of 7 applied (#4165)."""
    seen: dict[str, Any] = {}
    _tool_ok(monkeypatch, seen)
    ai_portfolios.fetch_ai_portfolio_grounding(model="cheap", run_date=date(2026, 6, 9))
    assert seen["recency_days"] == 7


@pytest.mark.unit
def test_an_operator_recency_days_change_reaches_the_tool_call(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """The #4165 repro: raising the knob to 30 must search 30 days, not keep 7."""
    seen: dict[str, Any] = {}
    _tool_ok(monkeypatch, seen)
    monkeypatch.setattr(
        ai_portfolios,
        "_config",
        lambda: {"accounts": [{"handle": "grkportfolio"}], "recency_days": 30},
    )
    ai_portfolios.fetch_ai_portfolio_grounding(model="cheap", run_date=date(2026, 6, 9))
    assert seen["recency_days"] == 30
    assert "last 30 days" in seen["query"]


@pytest.mark.unit
def test_a_non_integer_recency_days_warns_and_falls_back(
    monkeypatch: pytest.MonkeyPatch, caplog: pytest.LogCaptureFixture
) -> None:
    """A malformed yaml value must not traceback out of the pre-pass: warn and
    use the default window, matching web_grounding's config path (#4165)."""
    seen: dict[str, Any] = {}
    _tool_ok(monkeypatch, seen)
    monkeypatch.setattr(
        ai_portfolios,
        "_config",
        lambda: {"accounts": [{"handle": "grkportfolio"}], "recency_days": "seven"},
    )
    with caplog.at_level("WARNING", logger="digiquant.research.data.ai_portfolios"):
        ai_portfolios.fetch_ai_portfolio_grounding(model="cheap", run_date=date(2026, 6, 9))
    assert seen["recency_days"] == 7
    assert "last 7 days" in seen["query"]
    assert "recency_days" in caplog.text


@pytest.mark.unit
def test_fetch_ai_portfolio_grounding_raises_on_empty(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(
        ai_portfolios,
        "call_web_search_tool",
        lambda **k: (_ for _ in ()).throw(RuntimeError("no rows")),
    )
    with pytest.raises(DashboardWebSearchError):
        ai_portfolios.fetch_ai_portfolio_grounding(model="cheap", run_date=date(2026, 6, 9))


@pytest.mark.unit
def test_fetch_ai_portfolio_grounding_raises_on_blank_summary(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    seen: dict[str, Any] = {}
    _tool_ok(monkeypatch, seen, summary="   ", sources=[])
    with pytest.raises(DashboardWebSearchError):
        ai_portfolios.fetch_ai_portfolio_grounding(model="cheap", run_date=date(2026, 6, 9))


@pytest.mark.unit
def test_fetch_ai_portfolio_grounding_raises_on_missing_roster(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(ai_portfolios, "_config", lambda: {"accounts": [], "recency_days": 7})
    with pytest.raises(DashboardWebSearchError):
        ai_portfolios.fetch_ai_portfolio_grounding(model="cheap", run_date=date(2026, 6, 9))
