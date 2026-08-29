"""Tests for Hermes turnover discipline (#859 Phase D).

WP8.5 (#2738): cadence/turnover composition with the post-cutover H8 shell is locked
in ``test_allocation_invariants.py``.
"""

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


def test_relative_band_protects_large_position_from_small_drift() -> None:
    # 30% position sized to 33% = 3pp drift. The absolute 3pp floor alone would trade,
    # but the 20% relative band (= 6pp on a 30% name) holds it — no churn (#934).
    sized = apply_turnover_to_sized_book(
        {"SPY": 33.0},
        current_weights={"SPY": 30.0},
        prior_book=[{"ticker": "SPY", "entry_date": "2026-06-01"}],
        preferences={
            "rebalance_threshold_pct": 3,
            "rebalance_rel_band_pct": 20,
            "holding_days": 5,
        },
        run_date=date(2026, 6, 19),
    )
    assert sized["SPY"] == 30.0


def test_incumbent_turnover_preference_defaults_frozen() -> None:
    """WP6.1 (#2687): document turnover/cadence defaults exercised by H8 backstop."""
    from tests.dq.hermes.incumbent_risk_fixtures import load_incumbent_risk_fixture

    prefs = load_incumbent_risk_fixture()["policy_defaults"]["turnover_preferences"]
    assert prefs["rebalance_threshold_pct"] == 3
    assert prefs["holding_days"] == 5
    assert prefs["rebalance_rel_band_pct"] == 20
    assert prefs["rebalancing_cadence"] == "daily"


def test_relative_band_allows_large_drift() -> None:
    # 30% → 40% = 10pp drift breaches the 6pp band → rebalances to target.
    sized = apply_turnover_to_sized_book(
        {"SPY": 40.0},
        current_weights={"SPY": 30.0},
        prior_book=[{"ticker": "SPY", "entry_date": "2026-06-01"}],
        preferences={
            "rebalance_threshold_pct": 3,
            "rebalance_rel_band_pct": 20,
            "holding_days": 5,
        },
        run_date=date(2026, 6, 19),
    )
    assert sized["SPY"] == 40.0


def test_clamp_no_trade_band_snaps_post_cap_micro_deltas() -> None:
    from digiquant.olympus.hermes.turnover import clamp_no_trade_band

    out = clamp_no_trade_band(
        {"SPY": 20.15, "QQQ": 25.0},
        current_weights={"SPY": 20.0, "QQQ": 20.0},
        preferences={"rebalance_threshold_pct": 3, "rebalance_rel_band_pct": 20},
    )
    assert out["SPY"] == 20.0  # 0.15pp inside band
    assert out["QQQ"] == 25.0  # 5pp breaches 3pp floor / 4pp rel → kept


def test_ledger_decision_uses_no_trade_band_for_continuing_names() -> None:
    from digiquant.olympus.hermes.models.portfolio_ledger import DecisionAction
    from digiquant.olympus.hermes.writers.ledger_io import _decision

    action, _ = _decision(symbol="SPY", prior_pct=20.0, target_pct=20.2)
    assert action is DecisionAction.NO_OP
    action, _ = _decision(symbol="SPY", prior_pct=20.0, target_pct=25.0)
    assert action is DecisionAction.ADD
    action, _ = _decision(symbol="SPY", prior_pct=20.0, target_pct=0.0)
    assert action is DecisionAction.EXIT
    action, _ = _decision(symbol="NEW", prior_pct=0.0, target_pct=2.0)
    assert action is DecisionAction.ADD
