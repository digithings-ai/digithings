from __future__ import annotations

from datetime import date
from unittest.mock import patch

import pytest

pytest.importorskip("openai")  # ai_portfolios -> digigraph.llm needs openai (absent in dq-only CI)

from digiquant.olympus.atlas.data import ai_portfolios  # noqa: E402


@pytest.mark.unit
def test_fetch_ai_portfolio_grounding_returns_summary_sources_handles():
    captured = {}

    def _xs(model, query, *, max_results=12):
        captured["query"] = query
        return (
            "@grkportfolio bought $GFI[[1]](https://x.com/grkportfolio/status/1)",
            ["https://x.com/grkportfolio/status/1"],
        )

    with patch.object(ai_portfolios, "x_search", side_effect=_xs):
        out = ai_portfolios.fetch_ai_portfolio_grounding(
            model="openrouter/openrouter/auto", run_date=date(2026, 6, 9)
        )
    assert out is not None
    assert "$GFI" in out["summary"]
    assert out["sources"] == ["https://x.com/grkportfolio/status/1"]
    assert out["as_of"] == "2026-06-09"
    assert out["accounts"]  # the tracked handles, for transparency
    # every configured handle is named in the query so all latest posts are read
    for h in ("theaiportfolios", "grkportfolio", "ralliesarena", "geminiportfolio"):
        assert h in captured["query"]


@pytest.mark.unit
def test_fetch_ai_portfolio_grounding_none_for_non_xai():
    with patch.object(ai_portfolios, "x_search", return_value=None):
        assert (
            ai_portfolios.fetch_ai_portfolio_grounding(
                model="ollama/local", run_date=date(2026, 6, 9)
            )
            is None
        )


@pytest.mark.unit
def test_fetch_ai_portfolio_grounding_none_on_empty():
    with patch.object(ai_portfolios, "x_search", return_value=("  ", [])):
        assert (
            ai_portfolios.fetch_ai_portfolio_grounding(
                model="openrouter/openrouter/auto", run_date=date(2026, 6, 9)
            )
            is None
        )
