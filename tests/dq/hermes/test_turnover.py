"""Tests for Hermes turnover discipline (#859 Phase D)."""

from __future__ import annotations

from datetime import date

import pytest

from digiquant.olympus.hermes.turnover import apply_turnover_to_sized_book

pytestmark = pytest.mark.unit


def test_small_delta_below_threshold_holds_current_weight() -> None:
    sized = apply_turnover_to_sized_book(
        {"SPY": 18.0},
        current_weights={"SPY": 20.0},
        prior_book=[{"ticker": "SPY", "weight_pct": 20, "entry_date": "2026-06-01"}],
        preferences={"rebalance_threshold_pct": 3, "holding_days": 5},
        run_date=date(2026, 6, 19),
    )
    assert sized["SPY"] == 20.0


def test_exit_blocked_inside_min_hold_window() -> None:
    sized = apply_turnover_to_sized_book(
        {"SPY": 0.0},
        current_weights={"SPY": 20.0},
        prior_book=[{"ticker": "SPY", "weight_pct": 20, "entry_date": "2026-06-17"}],
        preferences={"rebalance_threshold_pct": 3, "holding_days": 5},
        run_date=date(2026, 6, 19),
    )
    assert sized["SPY"] == 20.0


def test_exit_allowed_after_min_hold_window() -> None:
    sized = apply_turnover_to_sized_book(
        {"SPY": 0.0},
        current_weights={"SPY": 20.0},
        prior_book=[{"ticker": "SPY", "weight_pct": 20, "entry_date": "2026-06-01"}],
        preferences={"rebalance_threshold_pct": 3, "holding_days": 5},
        run_date=date(2026, 6, 19),
    )
    assert sized["SPY"] == 0.0
