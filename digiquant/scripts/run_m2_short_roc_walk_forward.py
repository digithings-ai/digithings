#!/usr/bin/env python3
"""Stage 3/4 gate check for a shorter M2 rate-of-change lookback.

Context: Chris's read of the m2 diagnostic chart is that a shorter ROC
period (he suspects ~90d) tracks BTC price better than the current
365-day default, and that the rolling-z window on top of the ROC is a
separate smoothing knob he'd widen to compensate. A finer in-sample sweep
(run inline, not saved) over roc_days in {30,45,60,75,90,105,120} crossed
with m2_window in {90,120,150,180,250,365,500} found the best combined
cycle-overlap score at roc_days=60, m2_window=90 (score 147.90 vs. the
code defaults' 137.66) -- a shorter ROC than Chris's 90-day guess, and
*without* extra z-window smoothing (wider windows scored worse, not
better). This is a different candidate than the one already rejected by
run_baseline_joint_period_stage34.py (trend_window=500, m2_roc_days=270,
m2_window=150, dxy_window=60, which failed OOS at +52.22% vs baseline's
+84.90%) -- this run isolates the m2 ROC/window change alone, leaving
power_law trend_window and dxy_window at their existing code defaults, so
a failure or pass here is attributable to the m2 change specifically.

Diagnostic only. Not touching settings.json/RESEARCH_STATE.md -- report
the table back to Chris for explicit accept/reject per the standing gate.

Usage:
    uv run python -m scripts.run_m2_short_roc_walk_forward
"""

from __future__ import annotations

import functools
from pathlib import Path

import polars as pl

from digiquant.strategies.sdca.btc_power_law import BtcPowerLawRiskModel, load_coefficients
from digiquant.strategies.sdca.curve_optimize import search_wide_knee_curve
from digiquant.strategies.sdca.curve_sim import evaluate_sdca_trial_curve_sim
from digiquant.strategies.sdca.indicator_catalog import SdcaCompositeWeights, dxy_z, m2_liquidity_z
from digiquant.strategies.sdca.optimize import (
    SDCA_SHAPE_DEFAULTS,
    btc_power_law_rails_fitter,
    load_sdca_extra_sources,
    load_sdca_extra_z,
    load_sdca_ohlcv,
    run_sdca_walk_forward,
)
from digiquant.strategies.sdca.power_law_zscore import power_law_confluence_z
from digiquant.strategies.sdca.price_oscillators import SdcaOscillatorSpec
from digiquant.strategies.sdca.stage_a import risk_from_weighted_z

DIGIQUANT_ROOT = Path(__file__).resolve().parents[1]
DEFAULT_CACHE_DIR = DIGIQUANT_ROOT / "data" / "price-history"

TREND_WINDOW = 180  # power_law left at code default -- isolate the m2 ROC change only
M2_ROC_DAYS_CANDIDATES = (45, 60, 75)
M2_WINDOW = 90
DXY_WINDOW = 90

BASELINE_WEIGHTS = SdcaCompositeWeights(power_law=1.0, m2=0.5, dxy=0.5)


def print_wf_row(label: str, result) -> None:
    holdout = result.holdout_metrics.vs_flat_dca_pct if result.holdout_metrics else float("nan")
    print(
        f"{label:>40} | IS {result.mean_is_vs_flat_dca_pct:7.2f} | OOS {result.mean_oos_vs_flat_dca_pct:7.2f} "
        f"| gap {result.is_oos_gap_pct:7.2f} | holdout {holdout:7.2f} | beats_oos {str(result.beats_flat_dca_oos):>5}"
    )
    for fs in result.fold_scores:
        oos = fs.out_of_sample
        print(
            f"    fold {fs.fold.fold}: IS={fs.in_sample.vs_flat_dca_pct:8.2f}%  "
            f"OOS={oos.vs_flat_dca_pct:8.2f}%  feasible={fs.feasible}  "
            f"OOS_drawdown={oos.max_drawdown_pct:6.2f}%  OOS_capital_deployed={oos.capital_deployed_pct:6.2f}%"
        )
    if result.holdout_metrics is not None:
        h = result.holdout_metrics
        print(
            f"    holdout: vs_flat_dca={h.vs_flat_dca_pct:.2f}%  vs_lump={h.vs_lump_pct:.2f}%  "
            f"capital_deployed={h.capital_deployed_pct:.2f}%  max_drawdown={h.max_drawdown_pct:.2f}%"
        )
    print(
        f"    sensitivity: stable={result.sensitivity.stable}  "
        f"max_abs_delta_oos={result.sensitivity.max_abs_delta_oos_pct:.2f}pp"
    )


def run(cache_dir: Path = DEFAULT_CACHE_DIR) -> None:
    dates, prices = load_sdca_ohlcv(symbols=["BTC-USD"], data_path=None, data_dir=str(cache_dir))
    date_s = pl.Series("date", dates, dtype=pl.Date)
    price_s = pl.Series("price", prices, dtype=pl.Float64)
    print(f"BTC-USD {dates[0]}..{dates[-1]} ({len(dates)} daily bars)\n")

    sources = load_sdca_extra_sources(cache_dir)
    if sources.m2_dates is None or sources.dxy_dates is None:
        print("Missing m2/dxy sources -- cannot run.")
        return

    dxy_z_series = dxy_z(date_s, sources.dxy_dates, sources.dxy_values, window=DXY_WINDOW).to_list()
    risk_model = BtcPowerLawRiskModel(load_coefficients())
    rails = risk_model.rails(date_s)
    power_law_z = power_law_confluence_z(
        date_s, price_s, rails["low"], rails["median"], rails["high"], trend_window=TREND_WINDOW
    ).to_list()
    oscillators = SdcaOscillatorSpec(power_law_trend_window=TREND_WINDOW)

    print(f"BTC-USD {dates[0]}..{dates[-1]}  trend_window={TREND_WINDOW}  dxy_window={DXY_WINDOW}\n")
    print(f"{'validated baseline (defaults)':>44} | OOS   84.90 (curve_simulator) / 84.78 (nautilus)\n")

    for roc_days in M2_ROC_DAYS_CANDIDATES:
        m2_z = m2_liquidity_z(
            date_s, sources.m2_dates, sources.m2_values, roc_days=roc_days, window=M2_WINDOW
        ).to_list()
        risk = risk_from_weighted_z(dates, power_law_z, {"m2": m2_z, "dxy": dxy_z_series}, BASELINE_WEIGHTS)
        risk_s = pl.Series("risk", risk, dtype=pl.Float64)

        print(f"=== m2_roc_days={roc_days} m2_window={M2_WINDOW}: Stage 3 curve search ===")
        curve_result = search_wide_knee_curve(
            date_s, price_s, risk_s, initial_cash=1000.0, frozen_weights=BASELINE_WEIGHTS
        )
        best_shape = curve_result.best.shape
        shape_params = {
            "buy_max_rate": best_shape.buy_max_rate,
            "buy_knee_risk": best_shape.buy_knee_risk,
            "sell_knee_risk": best_shape.sell_knee_risk,
            "sell_max_rate": best_shape.sell_max_rate,
            "buy_curvature": best_shape.buy_curvature,
            "sell_curvature": best_shape.sell_curvature,
        }
        print(f"  winning shape: {shape_params}")
        print(
            f"  risk_adjusted_return={curve_result.best.risk_adjusted_return:.4f} "
            f"total_return_pct={curve_result.best.total_return_pct:.2f} "
            f"max_drawdown_pct={curve_result.best.max_drawdown_pct:.2f}"
        )

        print(f"=== m2_roc_days={roc_days}: Stage 4 curve_simulator walk-forward ===")
        extra_z = dict(load_sdca_extra_z(date_s, price_s, data_path=None, data_dir=str(cache_dir)))
        extra_z["m2"] = pl.Series("m2", m2_z)
        extra_z["dxy"] = pl.Series("dxy", dxy_z_series)

        trial = {**SDCA_SHAPE_DEFAULTS, **shape_params, "power_law_weight": 1.0, "m2_weight": 0.5, "dxy_weight": 0.5}
        bound_evaluator = functools.partial(evaluate_sdca_trial_curve_sim, oscillators=oscillators)
        result = run_sdca_walk_forward(
            dates,
            prices,
            [trial],
            rails_fitter=btc_power_law_rails_fitter,
            evaluator=bound_evaluator,
            evaluator_label=f"curve_simulator/m2_roc{roc_days}_win{M2_WINDOW}",
            extra_z=extra_z,
        )
        print_wf_row(f"m2_roc_days={roc_days} win={M2_WINDOW}", result)
        print()

    print(
        "Diagnostic only. Not touching RESEARCH_STATE.md/settings.json -- "
        "report back for Chris's explicit accept/reject."
    )


if __name__ == "__main__":
    run()
