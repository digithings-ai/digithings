#!/usr/bin/env python3
"""3-fold walk-forward validation of the weekly+monthly confluence candidate.

Final step of "index then curve, repeat" for this trial: the index half
(``run_weekly_monthly_confluence_composite_search.py``) picked weights +
oscillator periods over the Chris-approved 7-indicator pool (power_law, m2,
dxy, rs_eth, sma_band, weekly_monthly_rsi, weekly_monthly_macd, replacing
the old separate weekly/monthly RSI+MACD legs); the curve half
(``run_weekly_monthly_confluence_curve_search.py``) fit a wide-knee curve
against that frozen index and cleared the fast curve_simulator go/no-go
(+17% risk_adjusted_return over the published curve on the same index).

This script reports the number that actually matters per RESEARCH_STATE.md's
protocol: the fixed candidate (weights + oscillators + curve, all frozen,
none re-searched here) scored on the same 3-fold walk-forward split under
both evaluators (curve_simulator and Nautilus), same convention as the
documented "+84.90% OOS curve_simulator / +84.78% OOS nautilus" baseline.

``run_sdca_walk_forward`` is given a single-trial list -- it is not
re-searching, only scoring this one fixed candidate per fold.

Diagnostic only. No production writes -- does not touch RESEARCH_STATE.md,
settings.json, or presets.json. Report back to Chris for accept/reject.

Usage:
    uv run python scripts/run_weekly_monthly_confluence_walk_forward.py
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

# Stage 4 (3:1) winner from run_weekly_monthly_confluence_composite_search.py.
FROZEN_WEIGHT_PARAMS = {
    "power_law_weight": 1.0,
    "m2_weight": 0.25,
    "dxy_weight": 0.25,
    "rs_eth_weight": 0.25,
    "sma_band_weight": 0.25,
    "weekly_monthly_rsi_weight": 1.0,
    "weekly_monthly_macd_weight": 1.0,
}

# Stage 2 winning construction periods, same run.
FROZEN_OSCILLATORS = SdcaOscillatorSpec(
    power_law_trend_window=180,
    monthly_rsi_length=2,
    rsi_length=5,
    monthly_macd_fast=4,
    monthly_macd_slow=9,
    macd_fast=16,
    macd_slow=35,
    sma_band_window=120,
    sma_band_fast_window=30,
    rs_eth_window=60,
    rs_eth_fast_window=20,
)

# Wide-knee curve winner from run_weekly_monthly_confluence_curve_search.py.
FROZEN_SHAPE_PARAMS = {
    "buy_max_rate": 35.4425,
    "buy_knee_risk": 26.3481,
    "sell_knee_risk": 70.2778,
    "sell_max_rate": 59.2071,
    "buy_curvature": 1.0572,
    "sell_curvature": 4.8871,
}


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
    print(f"    sensitivity: stable={result.sensitivity.stable}  max_abs_delta_oos={result.sensitivity.max_abs_delta_oos_pct:.2f}pp")


def run(cache_dir: Path = DEFAULT_CACHE_DIR) -> None:
    dates, prices = load_sdca_ohlcv(symbols=["BTC-USD"], data_path=None, data_dir=str(cache_dir))
    extra_z = load_sdca_extra_z(
        dates, prices, data_path=None, data_dir=str(cache_dir), oscillators=FROZEN_OSCILLATORS
    )
    trial = {**SDCA_SHAPE_DEFAULTS, **FROZEN_SHAPE_PARAMS, **FROZEN_WEIGHT_PARAMS}

    print(f"BTC-USD {dates[0]}..{dates[-1]} ({len(dates)} daily bars)")
    print(f"frozen weights: {FROZEN_WEIGHT_PARAMS}")
    print(f"frozen oscillators: {FROZEN_OSCILLATORS.model_dump()}")
    print(f"frozen curve shape: {FROZEN_SHAPE_PARAMS}\n")

    print("=== curve_simulator evaluator (3-fold walk-forward, single frozen candidate) ===")
    result_cs = run_sdca_walk_forward(
        dates,
        prices,
        [trial],
        rails_fitter=btc_power_law_rails_fitter,
        evaluator=evaluate_sdca_trial_curve_sim,
        evaluator_label="curve_simulator/weekly_monthly_confluence",
        extra_z=extra_z,
    )
    print_wf_row("curve_simulator", result_cs)
    print()

    print("=== nautilus evaluator (3-fold walk-forward, single frozen candidate) ===")
    result_nt = run_sdca_walk_forward(
        dates,
        prices,
        [trial],
        rails_fitter=btc_power_law_rails_fitter,
        evaluator=evaluate_sdca_trial_nautilus,
        evaluator_label="nautilus/weekly_monthly_confluence",
        extra_z=extra_z,
    )
    print_wf_row("nautilus", result_nt)
    print()

    print("=== Summary (mean_OOS / holdout, vs-flat-DCA %) ===")
    print(
        f"{'RESEARCH_STATE.md current baseline':>40} | OOS  84.90 (curve_simulator) / 84.78 (nautilus) "
        f"| holdout n/a here (power_law/m2/dxy only, see RESEARCH_STATE.md)"
    )
    cs_holdout = result_cs.holdout_metrics.vs_flat_dca_pct if result_cs.holdout_metrics else float("nan")
    nt_holdout = result_nt.holdout_metrics.vs_flat_dca_pct if result_nt.holdout_metrics else float("nan")
    print(
        f"{'weekly_monthly_confluence (curve_sim)':>40} | OOS {result_cs.mean_oos_vs_flat_dca_pct:6.2f} "
        f"| holdout {cs_holdout:6.2f}"
    )
    print(
        f"{'weekly_monthly_confluence (nautilus)':>40} | OOS {result_nt.mean_oos_vs_flat_dca_pct:6.2f} "
        f"| holdout {nt_holdout:6.2f}"
    )
    print(
        "\nDiagnostic only. Not touching RESEARCH_STATE.md/settings.json -- "
        "report back for Chris's explicit accept/reject."
    )


if __name__ == "__main__":
    run()
