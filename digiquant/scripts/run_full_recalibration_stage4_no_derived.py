#!/usr/bin/env python3
"""No-derived-indicators variant: Stage 4 walk-forward OOS gate.

Follow-up to run_full_recalibration_stage2_no_derived.py, which excluded
weekly_monthly_rsi/weekly_monthly_macd from Stage 2's search entirely.
Winner (stable at 3:1/5:1 ratios, differs at 2:1): power_law=1.0,
monthly_rsi=1.0, everything else (rs_eth, weekly_rsi, weekly_macd,
sma_band, monthly_macd) floored at 0.1.

Note: unlike every prior variant, this Stage 2 result is NOT stable across
all three sensitivity ratios (sma_band flips to 1.0 at 2:1) -- report that
caveat alongside any Stage 4 result. Tests with the published curve shape
first (isolation-check style) before considering a fresh Stage 3 search.

Diagnostic only. Does not touch RESEARCH_STATE.md or settings.json.

Usage:
    uv run python scripts/run_full_recalibration_stage4_no_derived.py
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

# Stage 2 (no-derived) winner, stable at 3:1/5:1 ratios.
FROZEN_WEIGHT_PARAMS = {
    "power_law_weight": 1.0,
    "rs_eth_weight": 0.1,
    "weekly_rsi_weight": 0.1,
    "weekly_macd_weight": 0.1,
    "sma_band_weight": 0.1,
    "monthly_rsi_weight": 1.0,
    "monthly_macd_weight": 0.1,
    "weekly_monthly_rsi_weight": 0.0,
    "weekly_monthly_macd_weight": 0.0,
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
    trial = {**SDCA_SHAPE_DEFAULTS, **FROZEN_WEIGHT_PARAMS}

    print(f"BTC-USD {dates[0]}..{dates[-1]} ({len(dates)} daily bars)")
    print(f"frozen weights (Stage 2 no-derived winner): {FROZEN_WEIGHT_PARAMS}")
    print("curve shape: PUBLISHED DEFAULTS\n")

    print("=== curve_simulator evaluator (3-fold walk-forward) ===")
    result_cs = run_sdca_walk_forward(
        dates,
        prices,
        [trial],
        rails_fitter=btc_power_law_rails_fitter,
        evaluator=evaluate_sdca_trial_curve_sim,
        evaluator_label="curve_simulator/full_recalibration_no_derived",
        extra_z=extra_z,
    )
    print_wf_row("curve_simulator", result_cs)
    print()

    print("=== nautilus evaluator (3-fold walk-forward) ===")
    result_nt = run_sdca_walk_forward(
        dates,
        prices,
        [trial],
        rails_fitter=btc_power_law_rails_fitter,
        evaluator=evaluate_sdca_trial_nautilus,
        evaluator_label="nautilus/full_recalibration_no_derived",
        extra_z=extra_z,
    )
    print_wf_row("nautilus", result_nt)
    print()

    print("=== Summary (mean_OOS / holdout, vs-flat-DCA %) ===")
    print(
        f"{'RESEARCH_STATE.md current baseline':>40} | OOS  84.90 (curve_simulator) / 84.78 (nautilus) "
        f"| holdout n/a here"
    )
    cs_holdout = result_cs.holdout_metrics.vs_flat_dca_pct if result_cs.holdout_metrics else float("nan")
    nt_holdout = result_nt.holdout_metrics.vs_flat_dca_pct if result_nt.holdout_metrics else float("nan")
    print(f"{'no_derived (curve_sim)':>40} | OOS {result_cs.mean_oos_vs_flat_dca_pct:6.2f} | holdout {cs_holdout:6.2f}")
    print(f"{'no_derived (nautilus)':>40} | OOS {result_nt.mean_oos_vs_flat_dca_pct:6.2f} | holdout {nt_holdout:6.2f}")
    print(
        "\nDiagnostic only. Not touching RESEARCH_STATE.md/settings.json -- "
        "report back for Chris's explicit accept/reject, per the standing gate. "
        "NOTE: Stage 2 sensitivity was NOT stable across all ratios (sma_band flips at 2:1) -- "
        "treat any pass here as provisional pending a proper stability check."
    )


if __name__ == "__main__":
    run()
