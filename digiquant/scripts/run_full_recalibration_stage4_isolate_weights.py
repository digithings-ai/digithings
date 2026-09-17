#!/usr/bin/env python3
"""Isolation check: Stage 2 weights + PUBLISHED curve shape (not Stage 3's).

Stage 4 (run_full_recalibration_stage4.py) rejected the full Stage2+Stage3
candidate: OOS -13.38%/-13.43% vs the +84.90%/+84.78% baseline, with folds 1
and 2 flagged infeasible (near-zero/negative capital deployment) -- a sign
the Stage 3 wide-knee curve overfit in-sample (buy_max_rate=31.2,
sell_max_rate=8.09, aggressive knees).

This script isolates whether the FAILURE is driven by the curve shape or by
the Stage 2 weight mix itself: same frozen weights + oscillators, but using
SDCA_SHAPE_DEFAULTS's published curve shape (buy_max_rate=10,
buy_knee_risk=35, sell_knee_risk=80, sell_max_rate=10, buy_curvature=1,
sell_curvature=2) instead of the Stage 3 winner.

Diagnostic only. Does not touch RESEARCH_STATE.md or settings.json.

Usage:
    uv run python scripts/run_full_recalibration_stage4_isolate_weights.py
"""

from __future__ import annotations

from pathlib import Path

from digiquant.strategies.sdca.curve_sim import evaluate_sdca_trial_curve_sim
from digiquant.strategies.sdca.nautilus_evaluator import evaluate_sdca_trial_nautilus
from digiquant.strategies.sdca.optimize import (
    SDCA_SHAPE_DEFAULTS,
    btc_power_law_rails_fitter,
    load_sdca_extra_z,
    load_sdca_ohlcv,
    run_sdca_walk_forward,
)
from digiquant.strategies.sdca.price_oscillators import SdcaOscillatorSpec

DIGIQUANT_ROOT = Path(__file__).resolve().parents[1]
DEFAULT_CACHE_DIR = DIGIQUANT_ROOT / "data" / "price-history"

FROZEN_WEIGHT_PARAMS = {
    "power_law_weight": 0.1,
    "rs_eth_weight": 0.1,
    "weekly_rsi_weight": 0.1,
    "weekly_macd_weight": 0.1,
    "sma_band_weight": 0.1,
    "monthly_rsi_weight": 0.1,
    "monthly_macd_weight": 0.1,
    "weekly_monthly_rsi_weight": 1.0,
    "weekly_monthly_macd_weight": 1.0,
}

FROZEN_OSCILLATORS = SdcaOscillatorSpec(
    rsi_length=5,
    daily_rsi_length=5,
    macd_fast=16,
    macd_slow=35,
    macd_daily_fast=12,
    macd_daily_slow=26,
    sma_band_window=120,
    sma_band_fast_window=30,
    rs_eth_window=60,
    rs_eth_fast_window=20,
    power_law_trend_window=180,
    monthly_rsi_length=2,
    monthly_rsi_daily_length=14,
    monthly_macd_fast=4,
    monthly_macd_slow=9,
)


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
    print(f"    sensitivity: stable={result.sensitivity.stable}  max_abs_delta_oos={result.sensitivity.max_abs_delta_oos_pct:.2f}pp")


def run(cache_dir: Path = DEFAULT_CACHE_DIR) -> None:
    dates, prices = load_sdca_ohlcv(symbols=["BTC-USD"], data_path=None, data_dir=str(cache_dir))
    extra_z = load_sdca_extra_z(
        dates, prices, data_path=None, data_dir=str(cache_dir), oscillators=FROZEN_OSCILLATORS
    )
    # NOTE: only weight override -- SDCA_SHAPE_DEFAULTS's published curve shape stays.
    trial = {**SDCA_SHAPE_DEFAULTS, **FROZEN_WEIGHT_PARAMS}

    print(f"BTC-USD {dates[0]}..{dates[-1]} ({len(dates)} daily bars)")
    print(f"frozen weights (Stage 2 winner): {FROZEN_WEIGHT_PARAMS}")
    print("curve shape: PUBLISHED DEFAULTS (not Stage 3's overfit-suspect winner)\n")

    print("=== curve_simulator evaluator (3-fold walk-forward) ===")
    result_cs = run_sdca_walk_forward(
        dates,
        prices,
        [trial],
        rails_fitter=btc_power_law_rails_fitter,
        evaluator=evaluate_sdca_trial_curve_sim,
        evaluator_label="curve_simulator/stage2_weights_published_curve",
        extra_z=extra_z,
    )
    print_wf_row("curve_simulator", result_cs)
    print()

    print(
        "\nIsolation check only. If this still fails OOS, the Stage 2 weight mix "
        "itself (not the curve) is the problem -- likely the weekly_monthly_rsi/macd "
        "full-weight concentration overfitting to in-sample cycle structure."
    )


if __name__ == "__main__":
    run()
