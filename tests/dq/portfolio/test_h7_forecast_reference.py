"""WP4.5 (#2660): H7 binds ForecastReference from the current effective forecast map."""

from __future__ import annotations

from datetime import UTC, date, datetime
from decimal import Decimal
from unittest.mock import patch
from uuid import UUID

import pytest
from digiquant.portfolio.models.forecast import (
    AmendmentOutcome,
    EffectiveForecast,
    EffectiveSource,
    ForecastTerms,
    RawUncertainty,
    forecast_terms_content_hash,
)
from digiquant.portfolio.models.pm_direction import (
    ForecastReference,
    PMDirectionMemo,
    TickerDirection,
    bind_forecast_references,
)
from digiquant.portfolio.phases.h7_pm_direction import _bind_forecast_references, _h7_node
from digiquant.research.state import PhasePortfolioState, PriorContext, ResearchState

pytestmark = pytest.mark.unit

RUN_DATE = date(2026, 8, 25)
_TS = datetime(2026, 8, 25, 15, 0, tzinfo=UTC)
EFF_ID = UUID("33333333-3333-3333-3333-333333333333")
BASE_ID = UUID("44444444-4444-4444-4444-444444444444")
AMEND_ID = UUID("55555555-5555-5555-5555-555555555555")
LLM_FAKE_ID = UUID("99999999-9999-9999-9999-999999999999")


def _terms() -> ForecastTerms:
    return ForecastTerms(
        horizon_sessions=21,
        half_life_sessions=10,
        bear_return=Decimal("-0.08"),
        base_return=Decimal("0.05"),
        bull_return=Decimal("0.20"),
        bear_probability=Decimal("0.20"),
        base_probability=Decimal("0.55"),
        bull_probability=Decimal("0.25"),
        thesis_valid_probability=Decimal("0.70"),
        raw_uncertainty=RawUncertainty.LOW,
    )


def _effective(
    *,
    ticker: str = "AAPL",
    effective_id: UUID = EFF_ID,
    base_id: UUID = BASE_ID,
    amendment_id: UUID | None = AMEND_ID,
) -> EffectiveForecast:
    terms = _terms()
    source = EffectiveSource.AMENDMENT if amendment_id is not None else EffectiveSource.BASE
    return EffectiveForecast(
        effective_id=effective_id,
        ticker=ticker,
        base_forecast_id=base_id,
        amendment_id=amendment_id,
        source=source,
        terms=terms,
        content_hash=forecast_terms_content_hash(terms),
        amendment_outcome=(
            AmendmentOutcome.ACCEPTED if amendment_id is not None else AmendmentOutcome.NONE
        ),
        degradation_reason=None,
        effective_at=_TS,
        known_at=_TS,
    )


def _state(*, deliberation: dict | None = None) -> ResearchState:
    return ResearchState(
        run_type="delta",
        run_date=RUN_DATE,
        baseline_date=date(2026, 8, 24),
        prior_context=PriorContext(),
        phase_portfolio=PhasePortfolioState(deliberation_summaries=deliberation or {}),
    )


class TestBindForecastReferences:
    def test_bind_attaches_authoritative_ids(self) -> None:
        eff = _effective()
        memo = PMDirectionMemo(
            date=RUN_DATE,
            roster=[
                TickerDirection(ticker="AAPL", direction="long", conviction_rank=1),
                TickerDirection(ticker="CASH", direction="flat", conviction_rank=2),
            ],
        )
        bound = bind_forecast_references(
            memo,
            deliberation_by_ticker={
                "AAPL": {"ticker": "AAPL", "effective_forecast": eff.model_dump(mode="json")}
            },
        )
        aapl = bound.roster[0]
        assert aapl.direction == "long" and aapl.conviction_rank == 1
        assert aapl.forecast_reference is not None
        assert aapl.forecast_reference.effective_forecast_id == EFF_ID
        assert aapl.forecast_reference.base_forecast_id == BASE_ID
        assert aapl.forecast_reference.amendment_id == AMEND_ID
        cash = bound.roster[1].forecast_reference
        assert cash is not None
        assert cash.effective_forecast_id is None
        assert cash.degradation_reason == "forecast_unavailable"

    def test_bind_overwrites_model_supplied_ids(self) -> None:
        eff = _effective()
        memo = PMDirectionMemo(
            date=RUN_DATE,
            roster=[
                TickerDirection(
                    ticker="AAPL",
                    direction="flat",
                    conviction_rank=3,
                    forecast_reference=ForecastReference(
                        effective_forecast_id=LLM_FAKE_ID,
                        base_forecast_id=LLM_FAKE_ID,
                        amendment_id=None,
                        ticker="AAPL",
                    ),
                )
            ],
        )
        bound = bind_forecast_references(
            memo,
            deliberation_by_ticker={
                "AAPL": {"ticker": "AAPL", "effective_forecast": eff.model_dump(mode="json")}
            },
        )
        ref = bound.roster[0].forecast_reference
        assert ref is not None
        assert ref.effective_forecast_id == EFF_ID
        assert ref.effective_forecast_id != LLM_FAKE_ID
        assert bound.roster[0].direction == "flat"
        assert bound.roster[0].conviction_rank == 3

    def test_missing_forecast_is_explicit_degraded(self) -> None:
        memo = PMDirectionMemo(
            date=RUN_DATE,
            roster=[TickerDirection(ticker="AAPL", direction="long", conviction_rank=1)],
        )
        bound = bind_forecast_references(memo, deliberation_by_ticker={})
        ref = bound.roster[0].forecast_reference
        assert ref is not None
        assert ref.effective_forecast_id is None
        assert ref.base_forecast_id is None
        assert ref.degradation_reason == "forecast_unavailable"


class TestH7SuccessPathBinding:
    def test_successful_llm_path_binds_from_state_map(self) -> None:
        eff = _effective()
        state = _state(
            deliberation={
                "AAPL": {"ticker": "AAPL", "effective_forecast": eff.model_dump(mode="json")}
            }
        )
        llm_memo = PMDirectionMemo(
            date=date(2026, 1, 1),
            roster=[
                TickerDirection(
                    ticker="AAPL",
                    direction="long",
                    conviction_rank=1,
                    narrative="buy the dip",
                )
            ],
            memo="ok",
        )
        with patch(
            "digiquant.portfolio.phases.h7_pm_direction.run_research_agent",
            return_value=llm_memo,
        ):
            out = _h7_node(state)

        memo = out["phase_portfolio"].pm_direction_memo
        assert memo is not None
        assert memo.date == RUN_DATE
        row = memo.roster[0]
        assert row.direction == "long"
        assert row.conviction_rank == 1
        assert row.narrative == "buy the dip"
        assert row.forecast_reference is not None
        assert row.forecast_reference.effective_forecast_id == EFF_ID

    def test_phase_bind_wrapper_matches_model_helper(self) -> None:
        eff = _effective()
        state = _state(
            deliberation={
                "AAPL": {"ticker": "AAPL", "effective_forecast": eff.model_dump(mode="json")}
            }
        )
        memo = PMDirectionMemo(
            date=RUN_DATE,
            roster=[TickerDirection(ticker="AAPL", direction="long", conviction_rank=1)],
        )
        bound = _bind_forecast_references(memo, state)
        assert bound.roster[0].forecast_reference is not None
        assert bound.roster[0].forecast_reference.effective_forecast_id == EFF_ID
