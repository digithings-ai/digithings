"""H7 fail-soft (#1665): an LLM-output failure carries the prior memo, never raises.

WP4.5 (#2660): fail-soft must re-bind ForecastReference from *current* deliberation
IDs — a carried prior memo cannot retain stale forecast authority.
"""

from __future__ import annotations

from datetime import date
from unittest.mock import patch
from uuid import uuid4

import pytest
from digiquant.research.state import ResearchState, PhasePortfolioState, PriorContext
from digiquant.portfolio.models.pm_direction import (
    ForecastReference,
    PMDirectionMemo,
    TickerDirection,
)
from digiquant.portfolio.phases.h7_pm_direction import NODE_ID, _h7_node

pytestmark = pytest.mark.unit

RUN_DATE = date(2026, 7, 23)
PRIOR_EFF = uuid4()
PRIOR_BASE = uuid4()
CURRENT_EFF = uuid4()
CURRENT_BASE = uuid4()
PRIOR_MEMO_PAYLOAD = {
    "schema_version": "1.0",
    "date": "2026-07-22",
    "roster": [
        {
            "ticker": "SPY",
            "direction": "long",
            "conviction_rank": 1,
            "forecast_reference": {
                "ticker": "SPY",
                "effective_forecast_id": str(PRIOR_EFF),
                "base_forecast_id": str(PRIOR_BASE),
                "amendment_id": None,
                "degradation_reason": None,
            },
        },
        {"ticker": "TLT", "direction": "flat", "conviction_rank": 2},
    ],
    "memo": "prior direction",
}


def _state(*, with_prior_memo: bool, with_current_forecast: bool = False) -> ResearchState:
    latest = {"pm-direction-memo": {"payload": dict(PRIOR_MEMO_PAYLOAD)}} if with_prior_memo else {}
    deliberation: dict[str, dict[str, object]] = {}
    if with_current_forecast:
        deliberation["SPY"] = {
            "ticker": "SPY",
            "effective_forecast_id": str(CURRENT_EFF),
            "base_forecast_id": str(CURRENT_BASE),
            "amendment_id": None,
            "forecast_degradation": None,
        }
    return ResearchState(
        run_type="delta",
        run_date=RUN_DATE,
        baseline_date=date(2026, 7, 21),
        prior_context=PriorContext(latest_segments=latest),
        phase_portfolio=PhasePortfolioState(deliberation_summaries=deliberation),
    )


class TestH7FailSoft:
    def test_llm_failure_carries_prior_memo_without_raising(self) -> None:
        state = _state(with_prior_memo=True)
        with patch(
            "digiquant.portfolio.phases.h7_pm_direction.run_research_agent",
            side_effect=ValueError("Expecting value: line 201 column 1 (char 1100)"),
        ):
            out = _h7_node(state)

        memo = out["phase_portfolio"].pm_direction_memo
        assert memo is not None, "prior memo must be carried"
        assert memo.date == RUN_DATE, "carried memo must be re-dated to today"
        assert [e.ticker for e in memo.roster] == ["SPY", "TLT"]
        spy = next(e for e in memo.roster if e.ticker == "SPY")
        assert spy.forecast_reference is not None
        assert spy.forecast_reference.effective_forecast_id is None
        assert spy.forecast_reference.degradation_reason == "forecast_unavailable"
        errors = out.get("errors") or []
        assert len(errors) == 1
        assert errors[0].phase != "chain"
        assert errors[0].node == NODE_ID
        assert errors[0].retryable is False

    def test_llm_failure_without_prior_memo_degrades_to_none(self) -> None:
        state = _state(with_prior_memo=False)
        with patch(
            "digiquant.portfolio.phases.h7_pm_direction.run_research_agent",
            side_effect=ValueError("Expecting value: line 1 column 1 (char 0)"),
        ):
            out = _h7_node(state)

        assert out["phase_portfolio"].pm_direction_memo is None
        errors = out.get("errors") or []
        assert len(errors) == 1 and errors[0].phase != "chain"

    def test_llm_failure_rebinds_current_forecast_ids_not_prior(self) -> None:
        state = _state(with_prior_memo=True, with_current_forecast=True)
        with patch(
            "digiquant.portfolio.phases.h7_pm_direction.run_research_agent",
            side_effect=ValueError("Expecting value: line 1 column 1 (char 0)"),
        ):
            out = _h7_node(state)

        memo = out["phase_portfolio"].pm_direction_memo
        assert memo is not None
        spy = next(e for e in memo.roster if e.ticker == "SPY")
        assert spy.direction == "long"
        assert spy.conviction_rank == 1
        assert spy.forecast_reference is not None
        assert spy.forecast_reference.effective_forecast_id == CURRENT_EFF
        assert spy.forecast_reference.base_forecast_id == CURRENT_BASE
        assert spy.forecast_reference.effective_forecast_id != PRIOR_EFF

        tlt = next(e for e in memo.roster if e.ticker == "TLT")
        assert tlt.forecast_reference is not None
        assert tlt.forecast_reference.effective_forecast_id is None
        assert tlt.forecast_reference.degradation_reason == "forecast_unavailable"


class TestH7BindOnSuccess:
    def test_successful_llm_attaches_current_forecast_reference(self) -> None:
        state = _state(with_prior_memo=False, with_current_forecast=True)
        llm_memo = PMDirectionMemo(
            date=date(2026, 7, 22),
            roster=[
                TickerDirection(
                    ticker="SPY",
                    direction="long",
                    conviction_rank=1,
                    forecast_reference=ForecastReference(
                        ticker="SPY",
                        effective_forecast_id=PRIOR_EFF,
                        base_forecast_id=PRIOR_BASE,
                    ),
                )
            ],
            memo="fresh",
        )
        with patch(
            "digiquant.portfolio.phases.h7_pm_direction.run_research_agent",
            return_value=llm_memo,
        ):
            out = _h7_node(state)

        memo = out["phase_portfolio"].pm_direction_memo
        assert memo is not None
        assert memo.date == RUN_DATE
        ref = memo.roster[0].forecast_reference
        assert ref is not None
        assert ref.effective_forecast_id == CURRENT_EFF
        assert ref.base_forecast_id == CURRENT_BASE
        assert memo.roster[0].direction == "long"
        assert memo.roster[0].conviction_rank == 1
