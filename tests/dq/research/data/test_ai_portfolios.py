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
