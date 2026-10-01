"""Strict-box sell-mask builder causality + trial plumbing (#4804 Task 2).

The frozen box (z <= -2.0 & mayer-multiple >= 1.5) is the v6 sell veto. The
builder is causal by construction: the z leg uses the shipped trailing
``real_rate_z`` (forward-filled macro + trailing rolling window) and the
multiple leg uses a trailing-SMA mirror of ``measure_gold_mayer_multiple.py``.
These tests prove causality by truncation-equality across a regime break
(Plan-12 pattern from ``test_causal_rolling_folds.py``) and prove the test
itself is REAL by showing a future-peeking variant FAILS the same check —
a vacuous pass fails review.
"""

from __future__ import annotations

import importlib.util
import json
from datetime import date, timedelta
from pathlib import Path

import polars as pl
import pytest
from digiquant.strategies.sdca.curve_shape import SdcaCurveShape
from digiquant.strategies.sdca.curve_sim import evaluate_sdca_trial_curve_sim

pytestmark = pytest.mark.unit

SCRIPT_PATH = (
    Path(__file__).resolve().parents[4] / "digiquant" / "scripts" / "build_gold_sell_mask.py"
)
DATA_DIR = Path(__file__).resolve().parents[4] / "digiquant" / "data" / "price-history"
SCRATCH_DIR = Path(__file__).resolve().parents[4] / "digiquant" / ".scratch"

FROZEN_Z = -2.0
FROZEN_M = 1.5


def _load_builder():
    spec = importlib.util.spec_from_file_location("build_gold_sell_mask", SCRIPT_PATH)
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def _break_inputs(n: int = 140, break_at: int = 70) -> tuple[list[date], list[float], list[float]]:
    """Synthetic regime break: real yields crater, gold price steps up 2.6x.

    Post-break the trailing z of cratered yields goes deeply negative while
    the trailing-SMA multiple stays rich until the window fills — the mask
    fires on one side of the break only (non-vacuous by construction).
    """
    dates = [date(2016, 1, 1) + timedelta(days=i) for i in range(n)]
    dfii10 = [(2.5 if i < break_at else 0.1) for i in range(n)]
    closes = [(100.0 if i < break_at else 260.0) for i in range(n)]
    return dates, dfii10, closes


def _truncate_at(
    dates: list[date], dfii10: list[float], closes: list[float], t: int
) -> tuple[list[date], list[float], list[float]]:
    cutoff = dates[t]
    kept = [(d, f, c) for d, f, c in zip(dates, dfii10, closes, strict=True) if d <= cutoff]
    out_d = [d for d, _, _ in kept]
    return out_d, [f for _, f, _ in kept], [c for _, _, c in kept]


def test_mask_truncation_equality_across_regime_break() -> None:
    """mask[t] on full inputs == mask[t] on inputs truncated at t (REAL check)."""
    builder = _load_builder()
    dates, dfii10, closes = _break_inputs()
    full = builder.build_mask(
        dates,
        closes,
        dates,
        dfii10,
        z_window=30,
        sma_window=20,
    )
    assert any(full["mask"]) and not all(full["mask"])  # non-vacuous: fires and rests
    for t in (19, 40, 69, 70, 71, 80, 100, 139):
        trunc_d, trunc_f, trunc_c = _truncate_at(dates, dfii10, closes, t)
        trunc = builder.build_mask(
            trunc_d,
            trunc_c,
            trunc_d,
            trunc_f,
            z_window=30,
            sma_window=20,
        )
        assert trunc["mask"][-1] == full["mask"][t]
        assert trunc["z"][-1] == pytest.approx(full["z"][t])
        assert trunc["multiples"][-1] == pytest.approx(full["multiples"][t])


def test_leaky_centered_variant_fails_same_check() -> None:
    """The truncation check discriminates: a future-peeking multiple FAILS it.

    A centered SMA (uses closes after t) changes value when the calendar is
    truncated — proving the equality test above would catch lookahead rather
    than passing vacuously on any implementation.
    """
    _, _, closes = _break_inputs()

    def centered_multiples(values: list[float], window: int) -> list[float]:
        half = window // 2
        out = []
        for i in range(len(values)):
            win = values[max(0, i - half) : i + half + 1]
            out.append(values[i] / (sum(win) / len(win)))
        return out

    full = centered_multiples(closes, 20)
    diffs = 0
    for t in (60, 69, 70, 75):
        trunc = centered_multiples(closes[: t + 1], 20)
        if trunc[-1] != full[t]:
            diffs += 1
    assert diffs > 0


def test_frozen_box_grounds_on_real_inputs() -> None:
    """Builder on staged inputs: fires 2011-09-06, silent on 2020/2015 events."""
    builder = _load_builder()
    f_dates, f_vals = builder.read_dfii10_csv(DATA_DIR / "DFII10.csv")
    g_dates, g_closes = builder.read_gld_closes(DATA_DIR / "GLD-USD.csv")
    result = builder.build_mask(g_dates, g_closes, f_dates, f_vals)
    by_date = dict(zip(result["dates"], result["mask"], strict=True))
    assert by_date[date(2011, 9, 6)] is True
    assert by_date[date(2020, 8, 7)] is False
    assert by_date[date(2015, 12, 17)] is False
    assert by_date[g_dates[-1]] is False  # silent now
    # Mirror fidelity: trailing multiples match the staged series to 1e-6 and
    # the joint-day count agrees with the staged-series count exactly.
    staged = json.loads((SCRATCH_DIR / "gold_mayer_multiple.json").read_text())
    staged_by_date = {r["date"]: float(r["multiple"]) for r in staged["series"]}
    z_by_date = dict(zip(result["dates"], result["z"], strict=True))
    overlap = [
        (d, m)
        for d, m in zip(result["dates"], result["multiples"], strict=True)
        if m is not None and d.isoformat() in staged_by_date
    ]
    assert len(overlap) > 4000
    # Staged multiples are rounded to 4dp in the JSON (rounding, not drift).
    assert max(abs(m - staged_by_date[d.isoformat()]) for d, m in overlap) < 1e-4
    staged_joint = sum(1 for d, m in overlap if m >= FROZEN_M and z_by_date[d] <= FROZEN_Z)
    assert sum(result["mask"]) == staged_joint


class _TwoPhaseRails:
    """Cheap rails early (buys), rich rails late (sells) at flat prices."""

    def __init__(self, n: int, flip: int) -> None:
        self._flip = flip
        self._n = n

    def rails(self, dates: pl.Series) -> pl.DataFrame:
        n = dates.len()
        median = [200.0 if i < self._flip else 50.0 for i in range(n)]
        return pl.DataFrame(
            {"low": [m * 0.5 for m in median], "median": median, "high": [m * 2.0 for m in median]}
        )


def test_trial_evaluator_sell_dates_plumbing() -> None:
    """curve_sim kwarg: empty set vetoes sells, None == legacy exactly."""
    dates = [date(2021, 1, 1) + timedelta(days=i) for i in range(20)]
    prices = [100.0] * 20
    shape = SdcaCurveShape(
        buy_max_rate=35.0,
        buy_knee_risk=45.0,
        sell_knee_risk=65.0,
        sell_max_rate=30.0,
        buy_curvature=1.0,
        sell_curvature=1.0,
    )
    model = _TwoPhaseRails(20, 10)
    base = evaluate_sdca_trial_curve_sim(dates, prices, model, shape, 1.0, None)
    legacy = evaluate_sdca_trial_curve_sim(dates, prices, model, shape, 1.0, None, sell_dates=None)
    assert legacy.model_dump() == base.model_dump()
    vetoed = evaluate_sdca_trial_curve_sim(dates, prices, model, shape, 1.0, None, sell_dates=set())
    assert vetoed.model_dump() != base.model_dump()
    assert vetoed.capital_deployed_pct > base.capital_deployed_pct
