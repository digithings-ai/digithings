"""Mark-to-market drift + rebalancing cadence (#955).

Covers the two backend pieces: drifting the prior book to actual current weights
before the no-trade band runs, and the daily/weekly/monthly/none cadence gate.
Persistence of drifted weights to ``positions`` + the dashboard (scope items 4-5)
are deferred — they need an ``actual_pct`` schema decision (tracked separately).
"""

from __future__ import annotations

from datetime import date

import pytest

from digiquant.olympus.hermes.turnover import (
    apply_rebalancing_cadence,
    hold_drifted_book,
    mark_to_market_weights,
    should_rebalance_today,
)

pytestmark = pytest.mark.unit


class TestMarkToMarketWeights:
    def test_rally_increases_weight_and_shrinks_cash_share(self) -> None:
        # SPY 80%, CASH 20%; SPY +10% → value 88 vs cash 20, NAV 108.
        out = mark_to_market_weights({"SPY": 80.0, "CASH": 20.0}, {"SPY": 0.10})
        assert out["SPY"] == pytest.approx(88.0 / 108.0 * 100.0, abs=1e-3)
        assert out["CASH"] == pytest.approx(20.0 / 108.0 * 100.0, abs=1e-3)
        assert sum(out.values()) == pytest.approx(100.0, abs=1e-3)

    def test_cash_does_not_drift(self) -> None:
        out = mark_to_market_weights({"CASH": 100.0}, {"CASH": 0.5})
        assert out["CASH"] == pytest.approx(100.0)

    def test_no_deltas_is_identity(self) -> None:
        weights = {"SPY": 60.0, "TLT": 40.0}
        assert mark_to_market_weights(weights, {}) == pytest.approx(weights)

    def test_renormalizes_to_prior_gross(self) -> None:
        # Prior gross 90 (10% implicit cash gap); drift must preserve that gross.
        out = mark_to_market_weights({"SPY": 50.0, "TLT": 40.0}, {"SPY": 0.20, "TLT": -0.10})
        assert sum(out.values()) == pytest.approx(90.0, abs=1e-3)

    def test_empty_is_identity(self) -> None:
        assert mark_to_market_weights({}, {"SPY": 0.1}) == {}

    def test_degenerate_total_falls_back_to_input(self) -> None:
        # A -100% delta zeroes the only position → degenerate; return input unchanged.
        weights = {"SPY": 100.0}
        assert mark_to_market_weights(weights, {"SPY": -1.0}) == weights


class TestShouldRebalanceToday:
    _MON = date(2026, 6, 22)  # Monday
    _WED = date(2026, 6, 24)  # Wednesday

    def test_daily_always_true(self) -> None:
        assert should_rebalance_today("daily", self._WED) is True

    def test_none_always_false(self) -> None:
        assert should_rebalance_today("none", self._MON) is False

    def test_weekly_fires_on_anchor_weekday(self) -> None:
        assert should_rebalance_today("weekly", self._MON) is True  # default Monday
        assert should_rebalance_today("weekly", self._WED) is False

    def test_weekly_respects_configured_weekday(self) -> None:
        prefs = {"rebalance_weekday": 2}  # Wednesday
        assert should_rebalance_today("weekly", self._WED, prefs) is True
        assert should_rebalance_today("weekly", self._MON, prefs) is False

    def test_monthly_fires_on_anchor_day(self) -> None:
        assert should_rebalance_today("monthly", date(2026, 6, 1)) is True  # default day 1
        assert should_rebalance_today("monthly", date(2026, 6, 15)) is False

    def test_monthly_respects_configured_day(self) -> None:
        prefs = {"rebalance_day_of_month": 15}
        assert should_rebalance_today("monthly", date(2026, 6, 15), prefs) is True

    def test_monthly_anchor_above_28_is_clamped_to_28(self) -> None:
        # Anchors above 28 fire on the 28th (no true month-end firing) — documented clamp.
        prefs = {"rebalance_day_of_month": 31}
        assert should_rebalance_today("monthly", date(2026, 6, 28), prefs) is True
        assert should_rebalance_today("monthly", date(2026, 6, 30), prefs) is False

    def test_unknown_cadence_falls_back_to_daily(self) -> None:
        assert should_rebalance_today("fortnightly", self._WED) is True


class TestHoldDriftedBook:
    def test_continuing_position_holds_drifted_weight(self) -> None:
        # Sizer wants to trim SPY 30→25, but on a hold day it keeps the drifted 30.
        out = hold_drifted_book({"SPY": 25.0}, current_weights={"SPY": 30.0})
        assert out["SPY"] == 30.0

    def test_pm_exit_is_honored(self) -> None:
        out = hold_drifted_book({"SPY": 0.0}, current_weights={"SPY": 30.0})
        assert "SPY" not in out

    def test_new_entry_booked_at_target(self) -> None:
        out = hold_drifted_book({"NVDA": 12.0}, current_weights={"SPY": 30.0})
        assert out["NVDA"] == 12.0

    def test_empty_current_weights_is_passthrough(self) -> None:
        assert hold_drifted_book({"SPY": 25.0}, current_weights={}) == {"SPY": 25.0}

    def test_cash_dropped_from_book(self) -> None:
        out = hold_drifted_book({"CASH": 20.0, "SPY": 80.0}, current_weights={"SPY": 75.0})
        assert "CASH" not in out
        assert out["SPY"] == 75.0


class TestApplyRebalancingCadence:
    _RUN = date(2026, 6, 24)  # Wednesday

    def test_rebalance_day_applies_no_trade_band(self) -> None:
        # daily → rebalance path; a 10pp move exceeds the band → trade to target.
        out = apply_rebalancing_cadence(
            {"SPY": 40.0},
            current_weights={"SPY": 30.0},
            prior_book=[{"ticker": "SPY", "entry_date": "2026-01-01"}],
            preferences={"rebalancing_cadence": "daily"},
            run_date=self._RUN,
        )
        assert out["SPY"] == 40.0  # rebalanced to target

    def test_hold_day_holds_drifted_weight(self) -> None:
        # none → hold path; the same 10pp move is held at the drifted current weight.
        out = apply_rebalancing_cadence(
            {"SPY": 40.0},
            current_weights={"SPY": 30.0},
            prior_book=[{"ticker": "SPY", "entry_date": "2026-01-01"}],
            preferences={"rebalancing_cadence": "none"},
            run_date=self._RUN,
        )
        assert out["SPY"] == 30.0  # held, not rebalanced

    def test_default_cadence_is_daily(self) -> None:
        out = apply_rebalancing_cadence(
            {"SPY": 40.0},
            current_weights={"SPY": 30.0},
            prior_book=[{"ticker": "SPY", "entry_date": "2026-01-01"}],
            preferences={},  # no cadence set → daily
            run_date=self._RUN,
        )
        assert out["SPY"] == 40.0
