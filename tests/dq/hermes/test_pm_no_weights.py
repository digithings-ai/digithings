"""H7 PMDirectionMemo must not accept weight-bearing fields (PR 4c / §11.2).

WP4.5 (#2660): also reject forecast/weight mutation fields; ForecastReference is
bound deterministically after the LLM — never fabricated for missing lineage.
"""

from __future__ import annotations

from datetime import date
from uuid import uuid4

import pytest
from digiquant.olympus.hermes.models.pm_direction import (
    ForecastReference,
    PMDirectionMemo,
    TickerDirection,
    bind_forecast_references,
)
from pydantic import ValidationError

pytestmark = pytest.mark.unit


def test_pm_no_weights_valid_memo_accepts_direction_only() -> None:
    memo = PMDirectionMemo(
        date=date(2026, 6, 12),
        roster=[
            TickerDirection(
                ticker="SPY", direction="long", conviction_rank=1, narrative="top pick"
            ),
            TickerDirection(ticker="TLT", direction="flat", conviction_rank=2),
        ],
        memo="Risk-on tilt; no sizing.",
    )
    assert memo.roster[0].direction == "long"
    assert memo.roster[0].forecast_reference is None
    assert "target_pct" not in memo.model_dump()


def test_pm_no_weights_rejects_target_pct_on_memo() -> None:
    with pytest.raises(ValidationError, match="target_pct"):
        PMDirectionMemo.model_validate(
            {
                "schema_version": "1.0",
                "date": "2026-06-12",
                "roster": [],
                "target_pct": 25.0,
            }
        )


def test_pm_no_weights_rejects_recommended_portfolio_on_memo() -> None:
    with pytest.raises(ValidationError, match="recommended_portfolio"):
        PMDirectionMemo.model_validate(
            {
                "schema_version": "1.0",
                "date": "2026-06-12",
                "roster": [],
                "recommended_portfolio": [{"ticker": "SPY", "target_pct": 50.0}],
            }
        )


def test_pm_no_weights_rejects_weight_on_ticker_row() -> None:
    with pytest.raises(ValidationError, match="weight"):
        TickerDirection.model_validate(
            {
                "ticker": "SPY",
                "direction": "long",
                "conviction_rank": 1,
                "weight": 30.0,
            }
        )


def test_pm_rejects_expected_return_on_ticker_row() -> None:
    with pytest.raises(ValidationError, match="expected_return"):
        TickerDirection.model_validate(
            {
                "ticker": "SPY",
                "direction": "long",
                "conviction_rank": 1,
                "expected_return": 0.12,
            }
        )


def test_pm_rejects_target_weight_on_ticker_row() -> None:
    with pytest.raises(ValidationError, match="target_weight"):
        TickerDirection.model_validate(
            {
                "ticker": "SPY",
                "direction": "long",
                "conviction_rank": 1,
                "target_weight": 0.25,
            }
        )


def test_pm_rejects_forecast_mutation_fields_on_ticker_row() -> None:
    for forbidden in ("forecast_id", "base_return", "effective_forecast_id", "terms"):
        with pytest.raises(ValidationError, match=forbidden):
            TickerDirection.model_validate(
                {
                    "ticker": "SPY",
                    "direction": "long",
                    "conviction_rank": 1,
                    forbidden: "model-supplied",
                }
            )


def test_forecast_reference_ticker_must_match_decision() -> None:
    ref = ForecastReference(
        effective_forecast_id=uuid4(),
        base_forecast_id=uuid4(),
        amendment_id=None,
        ticker="TLT",
    )
    with pytest.raises(ValidationError, match="forecast_reference.ticker"):
        TickerDirection(
            ticker="SPY",
            direction="long",
            conviction_rank=1,
            forecast_reference=ref,
        )


def test_forecast_reference_accepts_matching_ticker() -> None:
    eff_id = uuid4()
    base_id = uuid4()
    row = TickerDirection(
        ticker="SPY",
        direction="long",
        conviction_rank=1,
        forecast_reference=ForecastReference(
            effective_forecast_id=eff_id,
            base_forecast_id=base_id,
            amendment_id=None,
            ticker="SPY",
            degradation_reason=None,
        ),
    )
    assert row.forecast_reference is not None
    assert row.forecast_reference.effective_forecast_id == eff_id
    assert row.forecast_reference.base_forecast_id == base_id


def test_bind_forecast_references_overwrites_model_supplied_ids() -> None:
    stale_eff = uuid4()
    current_eff = uuid4()
    current_base = uuid4()
    memo = PMDirectionMemo(
        date=date(2026, 8, 25),
        roster=[
            TickerDirection(
                ticker="SPY",
                direction="long",
                conviction_rank=1,
                forecast_reference=ForecastReference(
                    ticker="SPY",
                    effective_forecast_id=stale_eff,
                    base_forecast_id=uuid4(),
                ),
            )
        ],
    )
    bound = bind_forecast_references(
        memo,
        deliberation_by_ticker={
            "SPY": {
                "effective_forecast_id": str(current_eff),
                "base_forecast_id": str(current_base),
                "amendment_id": None,
            }
        },
    )
    ref = bound.roster[0].forecast_reference
    assert ref is not None
    assert ref.effective_forecast_id == current_eff
    assert ref.base_forecast_id == current_base
    assert bound.roster[0].direction == "long"
    assert bound.roster[0].conviction_rank == 1


def test_bind_forecast_references_missing_lineage_is_explicit_degraded() -> None:
    memo = PMDirectionMemo(
        date=date(2026, 8, 25),
        roster=[
            TickerDirection(
                ticker="SPY",
                direction="flat",
                conviction_rank=1,
                forecast_reference=ForecastReference(
                    ticker="SPY",
                    effective_forecast_id=uuid4(),
                    base_forecast_id=uuid4(),
                ),
            )
        ],
    )
    bound = bind_forecast_references(memo, deliberation_by_ticker={})
    ref = bound.roster[0].forecast_reference
    assert ref is not None
    assert ref.effective_forecast_id is None
    assert ref.base_forecast_id is None
    assert ref.degradation_reason == "forecast_unavailable"
    assert bound.roster[0].direction == "flat"
    assert bound.roster[0].conviction_rank == 1
