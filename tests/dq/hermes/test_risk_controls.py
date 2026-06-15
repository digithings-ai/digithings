"""Drawdown circuit breaker (Pillar 2).

``compute_breaker_scale`` maps a NAV series → a gross-exposure scale in [floor, 1.0]:
1.0 above the soft drawdown, a linear ramp to ``1 − max_reduction`` at the hard
drawdown. It only ever reduces (never levers up). ``breaker_scale_from_nav_history``
reads the recent ``nav_history`` window (look-ahead-guarded) and is fail-soft.
"""

from __future__ import annotations

from datetime import date

import pytest

from digiquant.olympus.hermes.risk_controls import (
    BreakerConfig,
    breaker_scale_from_nav_history,
    compute_breaker_scale,
)

from tests.dq.atlas.test_supabase_io import FakeSupabaseClient

pytestmark = pytest.mark.unit

AS_OF = date(2026, 6, 12)
_CFG = BreakerConfig()  # soft -8%, hard -20%, max_reduction 0.5


# --------------------------------------------------------------------------- pure compute


def test_fresh_book_has_no_cut() -> None:
    assert compute_breaker_scale([], config=_CFG).scale == 1.0
    assert compute_breaker_scale([100.0], config=_CFG).scale == 1.0


def test_shallow_drawdown_no_cut() -> None:
    # -5% drawdown is shallower than the -8% soft threshold → full exposure.
    state = compute_breaker_scale([100.0, 95.0], config=_CFG)
    assert state.scale == 1.0
    assert state.drawdown_pct == pytest.approx(-5.0)


def test_soft_threshold_boundary_no_cut() -> None:
    # Exactly at soft (-8%) → still no cut (ramp starts strictly beyond it).
    assert compute_breaker_scale([100.0, 92.0], config=_CFG).scale == 1.0


def test_hard_drawdown_takes_max_cut() -> None:
    # -25% (≤ hard -20%) → gross scaled to 1 − max_reduction = 0.5.
    state = compute_breaker_scale([100.0, 75.0], config=_CFG)
    assert state.scale == pytest.approx(0.5)
    assert state.drawdown_pct == pytest.approx(-25.0)


def test_linear_ramp_midpoint() -> None:
    # -14% is the midpoint of [-8, -20] → frac 0.5 → scale 1 − 0.5·0.5 = 0.75.
    state = compute_breaker_scale([100.0, 86.0], config=_CFG)
    assert state.scale == pytest.approx(0.75)


def test_peak_is_window_max_not_last_point() -> None:
    # Peak is the interior high (120), not the latest (90): dd = (90−120)/120 = −25%.
    state = compute_breaker_scale([100.0, 120.0, 90.0], config=_CFG)
    assert state.peak_nav == pytest.approx(120.0)
    assert state.scale == pytest.approx(0.5)


def test_new_high_is_full_exposure() -> None:
    state = compute_breaker_scale([100.0, 110.0, 120.0], config=_CFG)
    assert state.drawdown_pct == pytest.approx(0.0)
    assert state.scale == 1.0


def test_scale_never_exceeds_one() -> None:
    for navs in ([100.0, 130.0], [100.0, 100.0], [50.0, 200.0]):
        assert compute_breaker_scale(navs, config=_CFG).scale <= 1.0


def test_invalid_navs_filtered() -> None:
    # None / 0 / negative are dropped → clean series [100, 80] → −20% → 0.5.
    state = compute_breaker_scale([100.0, None, 0.0, -5.0, 80.0], config=_CFG)  # type: ignore[list-item]
    assert state.scale == pytest.approx(0.5)


# --------------------------------------------------------------------------- config


def test_from_preferences_normalizes_and_overrides() -> None:
    cfg = BreakerConfig.from_preferences(
        {
            "breaker_soft_dd_pct": 5,  # positive input → normalized to −5
            "breaker_hard_dd_pct": 15,
            "breaker_max_reduction": 0.8,
            "breaker_lookback_days": 90,
        }
    )
    assert cfg.soft_dd_pct == -5.0
    assert cfg.hard_dd_pct == -15.0
    assert cfg.max_reduction == 0.8
    assert cfg.lookback_days == 90


def test_from_preferences_defaults_when_absent() -> None:
    assert BreakerConfig.from_preferences({}) == BreakerConfig()


def test_max_reduction_clamped_to_unit_interval() -> None:
    assert BreakerConfig.from_preferences({"breaker_max_reduction": 5}).max_reduction == 1.0
    assert BreakerConfig.from_preferences({"breaker_max_reduction": -1}).max_reduction == 0.0


# --------------------------------------------------------------------------- I/O reader


def _nav_rows(pairs: list[tuple[str, float]]) -> list[dict]:
    return [{"date": d, "nav": n} for d, n in pairs]


def test_reads_window_and_computes_scale() -> None:
    client = FakeSupabaseClient(
        canned_reads={"nav_history": _nav_rows([("2026-06-01", 100.0), ("2026-06-10", 80.0)])}
    )
    state = breaker_scale_from_nav_history(client, AS_OF, config=_CFG)
    assert state.drawdown_pct == pytest.approx(-20.0)
    assert state.scale == pytest.approx(0.5)


def test_reader_look_ahead_guard_excludes_future_nav() -> None:
    # A future spike (after as_of) would create a 500 peak → huge drawdown if included.
    # The .lte(as_of) guard excludes it, so the peak stays 100 and dd is 0.
    client = FakeSupabaseClient(
        canned_reads={"nav_history": _nav_rows([("2026-06-10", 100.0), ("2026-06-20", 500.0)])}
    )
    state = breaker_scale_from_nav_history(client, AS_OF, config=_CFG)
    assert state.current_nav == pytest.approx(100.0)
    assert state.scale == 1.0


def test_reader_is_fail_soft_on_error() -> None:
    class _Raising:
        def table(self, _name: str):
            raise RuntimeError("supabase down")

    state = breaker_scale_from_nav_history(_Raising(), AS_OF, config=_CFG)
    assert state.scale == 1.0
    assert "failed" in state.reason
