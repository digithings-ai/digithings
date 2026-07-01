"""H6 deliberation skip tests (Olympus #930 PR 4b)."""

from __future__ import annotations

from datetime import date
from unittest.mock import patch

import pytest

from digigraph.graph.pipeline_builder import build_pipeline

from digiquant.olympus.atlas.state import (
    AtlasConfigBundle,
    AtlasResearchState,
    FocusRosterEntry,
    PhaseHermesState,
    PriorContext,
)
from digiquant.olympus.hermes.phases.h6_deliberation import build_h6_deliberation
from digiquant.olympus.hermes.ticker_fingerprint import news_hash_for_ticker


def _quiet_state() -> AtlasResearchState:
    news_hash = news_hash_for_ticker(
        AtlasResearchState(
            run_type="delta",
            run_date=date(2026, 6, 20),
            config=AtlasConfigBundle(watchlist=["AAPL"]),
        ),
        "AAPL",
    )
    state = AtlasResearchState(
        run_type="delta",
        run_date=date(2026, 6, 20),
        config=AtlasConfigBundle(watchlist=["AAPL"]),
        prior_context=PriorContext(
            prior_analyst_by_ticker={
                "AAPL": {
                    "date": "2026-06-19",
                    "stance": "hold",
                    "conviction_score": 1,
                    "fingerprint_news_hash": news_hash,
                }
            },
            latest_segments={
                "deliberation/AAPL": {
                    "date": "2026-06-19",
                    "payload": {
                        "ticker": "AAPL",
                        "conclusion": "prior agreement",
                        "net_stance": "neutral",
                        "conviction_delta": 0,
                    },
                }
            },
        ),
        price_deltas={"AAPL": 0.001},
    )
    state.phase_hermes = PhaseHermesState(
        focus_roster=[FocusRosterEntry(ticker="AAPL", roster_reason="held")],
        asset_analysts={
            "AAPL": {
                "ticker": "AAPL",
                "conviction_score": 1,
                "stance": "hold",
                "thesis": "unchanged",
                "risks": "",
                "sources": [],
            }
        },
    )
    return state


@pytest.mark.unit
class TestDeliberationSkip:
    def test_quiet_fingerprint_carries_summary_without_llm(self) -> None:
        compiled = build_pipeline(
            AtlasResearchState, [build_h6_deliberation(["AAPL"], held={"AAPL"})]
        )
        with patch(
            "digigraph.graph.research_agent.completion_text",
            side_effect=AssertionError("skip path must not call LLM"),
        ):
            result = compiled.invoke(_quiet_state())
        final = AtlasResearchState.model_validate(result)
        summary = final.phase_hermes.deliberation_summaries["AAPL"]
        assert summary["carried"] is True
        assert summary["conclusion"] == "prior agreement"

    def test_slim_carry_path_preserves_conclusion(self) -> None:
        """#925: the slim ``prior_deliberation_by_ticker`` carry (conclusion_excerpt)
        must land in the carried summary's ``conclusion`` — not an empty string."""
        news_hash = news_hash_for_ticker(
            AtlasResearchState(
                run_type="delta",
                run_date=date(2026, 6, 20),
                config=AtlasConfigBundle(watchlist=["AAPL"]),
            ),
            "AAPL",
        )
        state = AtlasResearchState(
            run_type="delta",
            run_date=date(2026, 6, 20),
            config=AtlasConfigBundle(watchlist=["AAPL"]),
            prior_context=PriorContext(
                prior_analyst_by_ticker={
                    "AAPL": {
                        "date": "2026-06-19",
                        "stance": "hold",
                        "conviction_score": 1,
                        "fingerprint_news_hash": news_hash,
                    }
                },
                # No latest_segments entry — only the slim carry from preflight.
                prior_deliberation_by_ticker={
                    "AAPL": {
                        "date": "2026-06-19",
                        "net_stance": "neutral",
                        "conviction_delta": 0,
                        "converged": True,
                        "conclusion_excerpt": "trim into strength; yields peaked",
                    }
                },
            ),
            price_deltas={"AAPL": 0.001},
        )
        state.phase_hermes = PhaseHermesState(
            focus_roster=[FocusRosterEntry(ticker="AAPL", roster_reason="held")],
            asset_analysts={
                "AAPL": {
                    "ticker": "AAPL",
                    "conviction_score": 1,
                    "stance": "hold",
                    "thesis": "unchanged",
                    "risks": "",
                    "sources": [],
                }
            },
        )
        compiled = build_pipeline(
            AtlasResearchState, [build_h6_deliberation(["AAPL"], held={"AAPL"})]
        )
        with patch(
            "digigraph.graph.research_agent.completion_text",
            side_effect=AssertionError("skip path must not call LLM"),
        ):
            result = compiled.invoke(state)
        final = AtlasResearchState.model_validate(result)
        summary = final.phase_hermes.deliberation_summaries["AAPL"]
        assert summary["carried"] is True
        assert summary["conclusion"] == "trim into strength; yields peaked"
