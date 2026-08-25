"""H7 fail-soft (#1665): an LLM-output failure carries the prior memo, never raises.

Three runs in two days (2026-07-21/22) died with ``chain/hermes: Expecting value: …``
— a research-agent JSON failure escaping a hermes node, marking the run failed and
burning ~$1.2–3.6 per outer retry. Every hermes LLM node is now fail-soft; this file
pins the H7 memo node (the highest-stakes one: no memo → no PM direction).

WP4.5 (#2660): fail-soft must re-bind ForecastReference from *current* effective
forecasts — a carried prior memo cannot retain stale forecast authority.
"""

from __future__ import annotations

from datetime import UTC, date, datetime
from decimal import Decimal
from unittest.mock import patch
from uuid import UUID

import pytest
from digiquant.olympus.atlas.state import AtlasResearchState, PhaseHermesState, PriorContext
from digiquant.olympus.hermes.models.forecast import (
    AmendmentOutcome,
    EffectiveForecast,
    EffectiveSource,
    ForecastTerms,
    RawUncertainty,
    forecast_terms_content_hash,
)
from digiquant.olympus.hermes.phases.h7_pm_direction import NODE_ID, _h7_node

pytestmark = pytest.mark.unit

RUN_DATE = date(2026, 7, 23)
_TS = datetime(2026, 7, 23, 15, 0, tzinfo=UTC)
PRIOR_EFF = UUID("11111111-1111-1111-1111-111111111111")
PRIOR_BASE = UUID("22222222-2222-2222-2222-222222222222")
CURRENT_EFF = UUID("33333333-3333-3333-3333-333333333333")
CURRENT_BASE = UUID("44444444-4444-4444-4444-444444444444")
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


def _current_effective() -> EffectiveForecast:
    terms = ForecastTerms(
        horizon_sessions=21,
        half_life_sessions=10,
        bear_return=Decimal("-0.10"),
        base_return=Decimal("0.04"),
        bull_return=Decimal("0.15"),
        bear_probability=Decimal("0.25"),
        base_probability=Decimal("0.50"),
        bull_probability=Decimal("0.25"),
        thesis_valid_probability=Decimal("0.60"),
        raw_uncertainty=RawUncertainty.MEDIUM,
    )
    return EffectiveForecast(
        effective_id=CURRENT_EFF,
        ticker="SPY",
        base_forecast_id=CURRENT_BASE,
        amendment_id=None,
        source=EffectiveSource.BASE,
        terms=terms,
        content_hash=forecast_terms_content_hash(terms),
        amendment_outcome=AmendmentOutcome.NONE,
        degradation_reason=None,
        effective_at=_TS,
        known_at=_TS,
    )


def _state(*, with_prior_memo: bool, with_current_forecast: bool = False) -> AtlasResearchState:
    latest = {"pm-direction-memo": {"payload": dict(PRIOR_MEMO_PAYLOAD)}} if with_prior_memo else {}
    deliberation: dict[str, dict[str, object]] = {}
    if with_current_forecast:
        deliberation["SPY"] = {
            "ticker": "SPY",
            "effective_forecast": _current_effective().model_dump(mode="json"),
            "effective_forecast_id": str(CURRENT_EFF),
            "base_forecast_id": str(CURRENT_BASE),
        }
    return AtlasResearchState(
        run_type="delta",
        run_date=RUN_DATE,
        baseline_date=date(2026, 7, 21),
        prior_context=PriorContext(latest_segments=latest),
        phase_hermes=PhaseHermesState(deliberation_summaries=deliberation),
    )


class TestH7FailSoft:
    def test_llm_failure_carries_prior_memo_without_raising(self) -> None:
        state = _state(with_prior_memo=True)
        with patch(
            "digiquant.olympus.hermes.phases.h7_pm_direction.run_research_agent",
            side_effect=ValueError("Expecting value: line 201 column 1 (char 1100)"),
        ):
            out = _h7_node(state)

        memo = out["phase_hermes"].pm_direction_memo
        assert memo is not None, "prior memo must be carried"
        assert memo.date == RUN_DATE, "carried memo must be re-dated to today"
        assert [e.ticker for e in memo.roster] == ["SPY", "TLT"]
        errors = out.get("errors") or []
        assert len(errors) == 1
        assert errors[0].phase != "chain", "must be a node-level error, not chain-fatal"
        assert errors[0].node == NODE_ID
        assert errors[0].retryable is False

    def test_llm_failure_without_prior_memo_degrades_to_none(self) -> None:
        state = _state(with_prior_memo=False)
        with patch(
            "digiquant.olympus.hermes.phases.h7_pm_direction.run_research_agent",
            side_effect=ValueError("Expecting value: line 1 column 1 (char 0)"),
        ):
            out = _h7_node(state)

        assert out["phase_hermes"].pm_direction_memo is None, "no prior → legacy sizing path"
        errors = out.get("errors") or []
        assert len(errors) == 1 and errors[0].phase != "chain"

    def test_llm_failure_rebinds_current_forecast_ids_not_prior(self) -> None:
        state = _state(with_prior_memo=True, with_current_forecast=True)
        with patch(
            "digiquant.olympus.hermes.phases.h7_pm_direction.run_research_agent",
            side_effect=ValueError("Expecting value: line 1 column 1 (char 0)"),
        ):
            out = _h7_node(state)

        memo = out["phase_hermes"].pm_direction_memo
        assert memo is not None
        spy = next(e for e in memo.roster if e.ticker == "SPY")
        assert spy.direction == "long"
        assert spy.conviction_rank == 1
        assert spy.forecast_reference is not None
        assert spy.forecast_reference.effective_forecast_id == CURRENT_EFF
        assert spy.forecast_reference.base_forecast_id == CURRENT_BASE
        assert spy.forecast_reference.effective_forecast_id != PRIOR_EFF

        tlt = next(e for e in memo.roster if e.ticker == "TLT")
        assert tlt.forecast_reference is None, "missing current lineage must not fabricate IDs"
