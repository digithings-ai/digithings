"""H4.5 coverage director — PM-directed analyst coverage (#3739)."""

from __future__ import annotations

from datetime import UTC, date, datetime
from typing import Any  # score:allow untyped any — scored-lint: heterogeneous phase-input dicts
from unittest.mock import patch

import pytest
from digiquant.portfolio.phases import coverage_director
from digiquant.portfolio.phases.coverage_director import CoverageDirective, CoverageSelection
from digiquant.research.state import (
    ExcludedTicker,
    FocusRosterEntry,
    PhasePortfolioState,
    PriorContext,
    ResearchConfigBundle,
    ResearchState,
)

pytestmark = pytest.mark.unit

_TS = datetime(2026, 9, 8, 16, 0, tzinfo=UTC)


def _state() -> ResearchState:
    state = ResearchState(
        run_type="baseline",
        run_date=date(2026, 9, 8),
        knowledge_cutoff_at=_TS,
        config=ResearchConfigBundle(
            watchlist=["AAPL", "SPY", "GLD", "TLT"],
            preferences={"max_positions": 5},
        ),
        prior_context=PriorContext(
            prior_book=[{"ticker": "AAPL", "weight": 0.05}, {"ticker": "SPY", "weight": 0.03}],
            active_theses=[],
        ),
    )
    state.phase_portfolio = PhasePortfolioState(
        focus_roster=[
            FocusRosterEntry(ticker="AAPL", roster_reason="held"),
            FocusRosterEntry(ticker="SPY", roster_reason="held"),
            FocusRosterEntry(
                ticker="GLD", roster_reason="thesis_mapped", linked_market_thesis_id="geo-gold"
            ),
        ],
        focus_roster_excluded=[],
    )
    return state


def _directive() -> CoverageDirective:
    return CoverageDirective(
        refresh=[CoverageSelection(ticker="AAPL", reason="earnings repriced the thesis today")],
        explore=[CoverageSelection(ticker="GLD", reason="gold thesis needs a vehicle check")],
        skip=[CoverageSelection(ticker="SPY", reason="quiet; last analysis stands")],
    )


def _run_node(state: ResearchState, directive_or_exc: Any) -> dict[str, Any]:
    with (
        patch.object(coverage_director, "load_skill_full", return_value="director skill"),
        patch.object(coverage_director, "_shared_context", return_value={}),
        patch.object(
            coverage_director,
            "run_research_agent",
            return_value=directive_or_exc,
            side_effect=None
            if isinstance(directive_or_exc, CoverageDirective)
            else directive_or_exc,
        ) as mocked_agent,
    ):
        result = coverage_director._coverage_director_node(state)
    return result, mocked_agent


class TestCoverageDirectorNode:
    def test_director_rewrites_roster_with_director_reasons(self) -> None:
        """Director refresh/explore become the H5 roster; skipped names leave with reasons."""
        state = _state()
        state.phase_portfolio = state.phase_portfolio.model_copy(
            update={
                "focus_roster_excluded": [
                    ExcludedTicker(
                        ticker="TLT", reason="not thesis-mapped and below technical screen"
                    )
                ]
            }
        )
        result, mocked_agent = _run_node(state, _directive())

        mocked_agent.assert_called_once()
        _, kwargs = mocked_agent.call_args
        assert kwargs["output_model"] is CoverageDirective
        assert kwargs["phase_slug"] == coverage_director.NODE_ID
        assert kwargs["tools"] is None

        roster = result["phase_portfolio"].focus_roster
        assert [(e.ticker, e.roster_reason) for e in roster] == [
            ("AAPL", "director_refresh"),
            ("GLD", "director_explore"),
        ]
        gld = next(e for e in roster if e.ticker == "GLD")
        assert gld.linked_market_thesis_id == "geo-gold"

        excluded = {e.ticker: e.reason for e in result["phase_portfolio"].focus_roster_excluded}
        assert excluded["SPY"] == "quiet; last analysis stands"
        assert "TLT" in excluded  # H4-rostered but director-omitted
        assert result.get("errors", []) == []

    def test_director_llm_failure_falls_back_to_h4_roster(self) -> None:
        """An LLM failure keeps H4's roster and records a non-retryable PhaseError."""
        state = _state()
        before = [(e.ticker, e.roster_reason) for e in state.phase_portfolio.focus_roster]
        result, _mocked = _run_node(state, RuntimeError("provider down"))

        assert "phase_portfolio" not in result
        assert [(e.ticker, e.roster_reason) for e in state.phase_portfolio.focus_roster] == before
        (err,) = result["errors"]
        assert err.phase == coverage_director.PHASE_NAME
        assert err.retryable is False

    def test_empty_h4_roster_skips_llm(self) -> None:
        """Nothing to direct — no LLM call, state untouched."""
        state = _state()
        state.phase_portfolio = state.phase_portfolio.model_copy(update={"focus_roster": []})
        result, mocked_agent = _run_node(state, _directive())

        mocked_agent.assert_not_called()
        assert result == {}
