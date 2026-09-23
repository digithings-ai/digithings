#!/usr/bin/env python3
"""Re-run of ``run_full_recalibration_fixed_index.py``'s Stage 4 walk-forward
OOS gate on a new trial: Stage 2b weights (unchanged) + the feasibility-aware
curve winner from ``curve_optimize_feasibility.
search_wide_knee_curve_feasibility_aware`` (SearchFeasible), in place of
Round 2's Stage 3b curve (fit on plain in-sample ``risk_adjusted_return``,
with no awareness of OOS capital-deployment feasibility).

Round 2 (``run_full_recalibration_fixed_index.py``, commit 60cf0777c) came
back ``beats_flat_dca_oos=True`` but ``sensitivity_stable=False``
(max_abs_delta_oos_pct=2.79 vs a 2.0 threshold), with only 1 of 3 OOS folds
feasible under the walk-forward gate's own capital-deployed/drawdown rails
-- REJECTED.

This script reuses Round 2's fixed-index plumbing byte-for-byte (same
``EXTRA_WINDOWS`` override, same Stage 1 oscillators, same Stage 2b weights,
same ``run_sdca_walk_forward`` / ``evaluate_sdca_trial_curve_sim`` /
``btc_power_law_rails_fitter`` call) and changes ONLY ``STAGE3B_CURVE`` to
the new curve params supplied for this trial:

    buy_max_rate=35, buy_knee_risk=30, sell_knee_risk=70, sell_max_rate=15,
    buy_curvature=1.5, sell_curvature=4

GATE (see RESEARCH_STATE.md "Standard trial protocol" step 6, and
``run_full_recalibration.py``'s own docstring): this script NEVER writes
``settings.json`` or RESEARCH_STATE.md's "Current best validated candidate"
section. It only qualifies as a candidate for that section once
``beats_flat_dca_oos=True`` AND the sensitivity report says ``stable=True``
-- and even then only on Chris's explicit accept, never this script's own
say-so.

Usage:
    uv run python scripts/run_full_recalibration_feasible_curve.py
"""

from __future__ import annotations

import functools
import json
from pathlib import Path

import polars as pl

from digiquant.strategies.sdca.btc_power_law import BtcPowerLawRiskModel, load_coefficients
from digiquant.strategies.sdca.curve_shape import SdcaCurveShape
from digiquant.strategies.sdca.curve_sim import evaluate_sdca_trial_curve_sim
from digiquant.strategies.sdca.cycle_windows import SdcaCycleWindows
from digiquant.strategies.sdca.indicator_catalog import SdcaCompositeWeights
from digiquant.strategies.sdca.optimize import (
    SdcaWalkForwardResult,
    btc_power_law_rails_fitter,
    load_sdca_extra_z,
    load_sdca_ohlcv,
    run_sdca_walk_forward,
)
from digiquant.strategies.sdca.power_law_zscore import power_law_confluence_z
from digiquant.strategies.sdca.price_oscillators import SdcaOscillatorSpec
from digiquant.strategies.sdca.two_stage import freeze_weight_params

DIGIQUANT_ROOT = Path(__file__).resolve().parents[1]
DEFAULT_DATA_PATH = DIGIQUANT_ROOT / "data" / "price-history" / "BTC-USD.csv"
OUT_PATH = DIGIQUANT_ROOT / ".scratch" / "full_recalibration_feasible_curve_walk_forward_result.json"

# ---------------------------------------------------------------------------
# Stage 1 winners -- unchanged from run_full_recalibration_fixed_index.py.
# ---------------------------------------------------------------------------
STAGE1_OSCILLATORS = SdcaOscillatorSpec(
    power_law_trend_window=180,
    rs_eth_window=60,
    rs_eth_fast_window=30,
    rsi_length=5,
    daily_rsi_length=5,
    macd_fast=12,
    macd_slow=26,
    macd_daily_fast=12,
    macd_daily_slow=26,
    sma_band_window=180,
    sma_band_fast_window=45,
    monthly_rsi_length=5,
    monthly_rsi_daily_length=5,
    monthly_macd_fast=4,
    monthly_macd_slow=9,
)

# ---------------------------------------------------------------------------
# Fixed-index correction -- identical to run_full_recalibration_fixed_index.py.
# ---------------------------------------------------------------------------
EXTRA_WINDOWS: dict[str, int] = {
    "dxy": 60,
    "onchain_mvrv": 365,
    "onchain_asopr": 365,
    "onchain_puell": 365,
    "onchain_rhodl": 365,
    "onchain_addr_ratio": 365,
    "fear_greed": 270,
}

# ---------------------------------------------------------------------------
# Stage 2b winner -- UNCHANGED from Round 2 (run_full_recalibration_fixed_index.py).
# ---------------------------------------------------------------------------
STAGE2B_WEIGHTS = SdcaCompositeWeights(
    power_law=0.1,
    m2=0.1,
    rs_eth=0.1,
    dxy=0.1,
    onchain_mvrv=0.95,
    onchain_asopr=0.1,
    onchain_puell=0.1,
    onchain_rhodl=1,
    onchain_addr_ratio=1,
    fear_greed=0.1,
    weekly_monthly_rsi=0.1,
    weekly_monthly_macd=1,
    weekly_rsi=0.1,
    weekly_macd=0.1,
    sma_band=0.1,
    monthly_rsi=0.1,
    monthly_macd=0.1,
)

# ---------------------------------------------------------------------------
# NEW this round: feasibility-aware curve winner from SearchFeasible
# (curve_optimize_feasibility.search_wide_knee_curve_feasibility_aware),
# supplied for this trial -- in place of Round 2's plain-risk_adjusted_return
# STAGE3B_CURVE.
# ---------------------------------------------------------------------------
STAGE3B_CURVE = SdcaCurveShape(
    buy_max_rate=35,
    buy_knee_risk=30,
    sell_knee_risk=70,
    sell_max_rate=15,
    buy_curvature=1.5,
    sell_curvature=4,
)


def print_stage1_summary(dates: list, prices: list) -> None:
    print("=== Stage 1: oscillator period winners (frozen, not re-searched) ===")
    for field, value in STAGE1_OSCILLATORS.model_dump().items():
        print(f"  {field}: {value}")

    date_s = pl.Series("date", dates, dtype=pl.Date)
    price_s = pl.Series("price", prices, dtype=pl.Float64)
    rails = BtcPowerLawRiskModel(load_coefficients()).rails(date_s)
    pl_z = power_law_confluence_z(
        date_s, price_s, rails["low"], rails["median"], rails["high"],
        trend_window=STAGE1_OSCILLATORS.power_law_trend_window,
    )
    z_stats = pl_z.drop_nulls()
    print(
        f"  power_law_confluence_z (trend_window={STAGE1_OSCILLATORS.power_law_trend_window}, "
        f"full-history diagnostic only): min={z_stats.min():.2f} median={z_stats.median():.2f} "
        f"max={z_stats.max():.2f}"
    )

    long_windows = SdcaCycleWindows.btc_v1()
    medium_windows = SdcaCycleWindows.btc_medium_term_v1()
    print(
        f"  cycle windows: long={len(long_windows.windows)} pins, "
        f"medium={len(medium_windows.windows)} pins (Stage 1/2 scoring context only)"
    )
    print(f"\n  extra_windows override (fixed-index correction): {EXTRA_WINDOWS}")


def print_stage2_summary() -> None:
    print("\n=== Stage 2b: 17-indicator floor-diversified aggregate reweight, fixed index (frozen, UNCHANGED) ===")
    for name, value in STAGE2B_WEIGHTS.model_dump().items():
        if value != 0.0:
            print(f"  {name}: {value:g}")


def print_stage3_summary() -> None:
    print("\n=== Stage 3b: feasibility-aware curve winner (SearchFeasible), NEW this round ===")
    for field, value in STAGE3B_CURVE.model_dump().items():
        print(f"  {field}: {value:g}")


def build_stage4_trial() -> dict[str, float | int | str]:
    """Stage 2b weights + feasibility-aware Stage 3b curve as one trial dict."""
    trial: dict[str, float | int | str] = dict(freeze_weight_params(STAGE2B_WEIGHTS))
    trial.update(STAGE3B_CURVE.model_dump())
    return trial


def load_stage4_inputs() -> tuple[list, list, dict]:
    dates, prices = load_sdca_ohlcv(symbols=["BTC-USD"], data_path=DEFAULT_DATA_PATH, data_dir=None)
    extra_z = load_sdca_extra_z(
        dates,
        prices,
        data_path=DEFAULT_DATA_PATH,
        data_dir=None,
        oscillators=STAGE1_OSCILLATORS,
        extra_windows=EXTRA_WINDOWS,
    )
    return dates, prices, extra_z


def run_stage4_walk_forward(dates: list, prices: list, extra_z: dict) -> SdcaWalkForwardResult:
    trial = build_stage4_trial()
    evaluator = functools.partial(evaluate_sdca_trial_curve_sim, oscillators=STAGE1_OSCILLATORS)
    return run_sdca_walk_forward(
        dates,
        prices,
        [trial],
        rails_fitter=btc_power_law_rails_fitter,
        evaluator=evaluator,
        evaluator_label="curve_simulator",
        extra_z=extra_z,
    )


def print_stage4_fold_table(result: SdcaWalkForwardResult) -> None:
    print(f"\n=== Stage 4: walk-forward OOS validation gate ({result.evaluator_label}) ===")
    print(f"{len(result.folds)} folds, holdout tail {result.holdout[0]}..{result.holdout[1]}\n")
    for fs in result.fold_scores:
        f = fs.fold
        is_m, oos_m = fs.in_sample, fs.out_of_sample
        print(
            f"  fold {f.fold}: IS {f.is_start}..{f.is_end}  OOS {f.oos_start}..{f.oos_end}\n"
            f"    IS  vs_flat_dca={is_m.vs_flat_dca_pct:+8.2f}%  vs_lump={is_m.vs_lump_pct:+8.2f}%  "
            f"capital_deployed={is_m.capital_deployed_pct:5.1f}%  max_dd={is_m.max_drawdown_pct:5.1f}%\n"
            f"    OOS vs_flat_dca={oos_m.vs_flat_dca_pct:+8.2f}%  vs_lump={oos_m.vs_lump_pct:+8.2f}%  "
            f"capital_deployed={oos_m.capital_deployed_pct:5.1f}%  max_dd={oos_m.max_drawdown_pct:5.1f}%  "
            f"oos_minus_is={oos_m.vs_flat_dca_pct - is_m.vs_flat_dca_pct:+6.2f}  feasible={fs.feasible}"
        )
    print(
        f"\n  mean IS vs_flat_dca={result.mean_is_vs_flat_dca_pct:+.2f}%  "
        f"mean OOS vs_flat_dca={result.mean_oos_vs_flat_dca_pct:+.2f}%  "
        f"IS-OOS gap (is_oos_gap_pct = mean_is - mean_oos)={result.is_oos_gap_pct:+.2f}"
    )
    print(f"  beats_flat_dca_oos={result.beats_flat_dca_oos}")
    if result.holdout_metrics is not None:
        h = result.holdout_metrics
        print(
            f"  holdout: vs_flat_dca={h.vs_flat_dca_pct:+.2f}%  vs_lump={h.vs_lump_pct:+.2f}%  "
            f"capital_deployed={h.capital_deployed_pct:.1f}%  max_dd={h.max_drawdown_pct:.1f}%"
        )
    s = result.sensitivity
    print(
        f"\n  sensitivity (+/-{s.frac:g} on every numeric param, {s.neighbor_count} valid neighbors):\n"
        f"    max_abs_delta_oos_pct={s.max_abs_delta_oos_pct:.2f}  "
        f"spike_threshold_pct={s.spike_threshold_pct:g}  stable={s.stable}"
    )
    print(f"\n  num_evaluations={result.num_evaluations}  objective={result.objective.model_dump()}")


def main() -> None:
    dates, prices, extra_z = load_stage4_inputs()
    print(f"BTC-USD {dates[0]}..{dates[-1]} ({len(dates)} daily bars)")
    print(f"extras available: {sorted(extra_z)}\n")

    print_stage1_summary(dates, prices)
    print_stage2_summary()
    print_stage3_summary()

    result = run_stage4_walk_forward(dates, prices, extra_z)
    print_stage4_fold_table(result)

    OUT_PATH.parent.mkdir(parents=True, exist_ok=True)
    OUT_PATH.write_text(json.dumps(result.model_dump(), indent=2, default=str))
    print(f"\nwrote {OUT_PATH}")

    qualifies = result.beats_flat_dca_oos and result.sensitivity.stable
    infeasible_folds = [fs.fold.fold for fs in result.fold_scores if not fs.feasible]
    print(
        f"\nOVERALL: beats_flat_dca_oos={result.beats_flat_dca_oos}  "
        f"sensitivity_stable={result.sensitivity.stable}  "
        f"qualifies_as_new_baseline_candidate={qualifies}"
    )
    if infeasible_folds:
        print(
            f"  NOTE: fold(s) {infeasible_folds} are infeasible under the objective's "
            f"capital-deployed floor / drawdown cap (SdcaOptimizeObjective) -- "
            f"mean_oos_vs_flat_dca_pct and beats_flat_dca_oos are plain averages over ALL "
            f"folds regardless of feasibility (see optimize.py's _mean_oos/_mean_is), so a "
            f"positive beats_flat_dca_oos here does not by itself mean every fold cleared the "
            f"feasibility rails -- check the per-fold feasible= flags above."
        )
    print(
        "\nDiagnostic walk-forward gate only -- this script NEVER writes settings.json or "
        "RESEARCH_STATE.md's \"current best validated candidate\" section, regardless of this "
        "result. Report this table to Chris for explicit accept/reject; qualifying for the gate "
        "(beats_flat_dca_oos=True AND sensitivity stable=True) is necessary but not sufficient -- "
        "only his explicit accept promotes a candidate."
    )


if __name__ == "__main__":
    main()
