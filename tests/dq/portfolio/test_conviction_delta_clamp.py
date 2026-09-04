"""H6 conviction_delta clamp (house GHA 33426508863 ``input_value=-3``)."""

from __future__ import annotations

import pytest
from digiquant.portfolio.models.deliberation import (
    DeliberationAnalystTurn,
    DeliberationPmTurn,
    DeliberationSummary,
)
from pydantic import ValidationError

pytestmark = pytest.mark.unit


def test_analyst_turn_clamps_minus_three_to_minus_two() -> None:
    """Live research_agent attempt 1/2 failed DeliberationAnalystTurn at -3."""
    turn = DeliberationAnalystTurn.model_validate(
        {
            "response": "Size cut is accepted; the BTC beta stays too high.",
            "conviction_delta": -3,
        }
    )
    assert turn.conviction_delta == -2


def test_pm_and_summary_clamp_the_same_bounds() -> None:
    pm = DeliberationPmTurn.model_validate({"challenge": "Correlation.", "conviction_delta": 4})
    summary = DeliberationSummary.model_validate(
        {"ticker": "BITO", "conclusion": "Trim.", "conviction_delta": -9}
    )
    assert pm.conviction_delta == 2
    assert summary.conviction_delta == -2


def test_in_range_delta_is_unchanged() -> None:
    turn = DeliberationAnalystTurn.model_validate({"conviction_delta": -1})
    assert turn.conviction_delta == -1


def test_non_numeric_delta_still_rejected() -> None:
    with pytest.raises(ValidationError, match="conviction_delta"):
        DeliberationAnalystTurn.model_validate({"conviction_delta": "hot"})


def test_bool_delta_is_rejected_on_all_three_models() -> None:
    with pytest.raises(ValidationError, match="conviction_delta"):
        DeliberationAnalystTurn.model_validate({"conviction_delta": True})
    with pytest.raises(ValidationError, match="conviction_delta"):
        DeliberationPmTurn.model_validate({"conviction_delta": True})
    with pytest.raises(ValidationError, match="conviction_delta"):
        DeliberationSummary.model_validate({"ticker": "BITO", "conviction_delta": True})
