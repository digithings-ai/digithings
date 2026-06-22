"""H7 PMDirectionMemo must not accept weight-bearing fields (PR 4c / §11.2)."""

from __future__ import annotations

from datetime import date

import pytest
from pydantic import ValidationError

from digiquant.olympus.hermes.models.pm_direction import PMDirectionMemo, TickerDirection

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
