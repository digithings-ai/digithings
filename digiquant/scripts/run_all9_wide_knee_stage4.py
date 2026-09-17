#!/usr/bin/env python3
"""Stage 4 (OOS walk-forward) on the all-9 floor-diversified wide-knee
candidate documented in ``RESEARCH_STATE.md`` items 6 and 8.

That thread (`run_dual_timeframe_composite_search.py` +
`run_curve_wide_knee_search.py`) built and curve-fit a 9-indicator
floor-diversified composite (`power_law=1.0, sma_band=1.0, monthly_rsi=1.0`
at the ceiling; `m2, rs_eth, dxy, weekly_rsi, weekly_macd, monthly_macd`
floored at `0.25`) with a wide-knee buy/sell curve
(`buy_knee_risk=40, sell_knee_risk=70, buy_max_rate=35, sell_max_rate=30,
buy_curvature=1.5, sell_curvature=1.5`) that beat the validated baseline's
in-sample tearsheet numbers (net_profit_pct=3406.71% vs. the baseline's much
smaller in-sample figure) -- but was explicitly logged as **"diagnostic
only, in-sample, beats_flat_dca_oos=False, not a validated trading
candidate"** and was never actually run through Stage 4 OOS walk-forward.
This script closes that gap: freeze the exact weights, oscillator periods
(picked up individually across that thread's Stage 1/2b passes), and curve
shape, then run the standard 3-fold walk-forward to get a real
in-sample/out-of-sample table instead of the single full-history in-sample
number that thread stopped at.

``monthly_rsi``/``monthly_macd`` are already real, fully-wired members of
``EXTRA_INDICATOR_NAMES`` (not dormant placeholders, despite
``RESEARCH_STATE.md`` calling them diagnostic-only pending a
production-config decision) -- ``load_sdca_extra_z``/``run_sdca_walk_forward``
already support them natively via the ``oscillators`` override. No plumbing
gaps this time.

Per the standing gate: diagnostic only, does not touch settings.json or
RESEARCH_STATE.md. Report the table back to Chris for explicit accept/reject.

Usage:
    uv run python -m scripts.run_all9_wide_knee_stage4
"""

from __future__ import annotations

from pathlib import Path

from digiquant.strategies.sdca.curve_sim import evaluate_sdca_trial_curve_sim
from digiquant.strategies.sdca.indicator_catalog import SdcaCompositeWeights
from digiquant.strategies.sdca.optimize import (
    btc_power_law_rails_fitter,
    load_sdca_extra_z,
    load_sdca_ohlcv,
    run_sdca_walk_forward,
)
from digiquant.strategies.sdca.price_oscillators import SdcaOscillatorSpec

DIGIQUANT_ROOT = Path(__file__).resolve().parents[1]
DEFAULT_CACHE_DIR = DIGIQUANT_ROOT / "data" / "price-history"

# RESEARCH_STATE.md item 6, Sixth pass -- winning floor-diversified mix (3:1/2:1/5:1 all agree).
ALL9_FLOOR_DIVERSIFIED_WEIGHTS = SdcaCompositeWeights(
    power_law=1.0,
    sma_band=1.0,
    monthly_rsi=1.0,
    m2=0.25,
    rs_eth=0.25,
    dxy=0.25,
    weekly_rsi=0.25,
    weekly_macd=0.25,
    monthly_macd=0.25,
)

# Individually period-searched periods (item 6, second/third passes):
# weekly_rsi -> weekly_length=5, daily_length=5; weekly_macd -> 16/35/12/26;
# sma_band -> 120/30 (first pass); monthly_rsi -> monthly_length=2 (shares
# daily_rsi_length with weekly_rsi=5); monthly_macd -> 4/9 (shares
# macd_daily_fast/slow=12/26 with weekly_macd).
ALL9_OSCILLATORS = SdcaOscillatorSpec(
    rsi_length=5,
    daily_rsi_length=5,
    macd_fast=16,
    macd_slow=35,
    macd_daily_fast=12,
    macd_daily_slow=26,
    sma_band_window=120,
    sma_band_fast_window=30,
    monthly_rsi_length=2,
    monthly_macd_fast=4,
    monthly_macd_slow=9,
)

# RESEARCH_STATE.md item 8 -- wide-knee search winner on this exact index.
ALL9_WIDE_KNEE_SHAPE = {
    "buy_max_rate": 35.0,
    "buy_knee_risk": 40.0,
    "sell_knee_risk": 70.0,
    "sell_max_rate": 30.0,
    "buy_curvature": 1.5,
    "sell_curvature": 1.5,
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
    print(
        f"    sensitivity: stable={result.sensitivity.stable}  "
        f"max_abs_delta_oos={result.sensitivity.max_abs_delta_oos_pct:.2f}pp"
    )


def run(cache_dir: Path = DEFAULT_CACHE_DIR) -> None:
    dates, prices = load_sdca_ohlcv(symbols=["BTC-USD"], data_path=None, data_dir=str(cache_dir))
    print(f"BTC-USD {dates[0]}..{dates[-1]} ({len(dates)} daily bars)\n")
    print(f"frozen weights: {ALL9_FLOOR_DIVERSIFIED_WEIGHTS.model_dump()}")
    print(f"frozen curve shape: {ALL9_WIDE_KNEE_SHAPE}\n")

    extra_z = load_sdca_extra_z(
        dates, prices, data_path=None, data_dir=str(cache_dir), oscillators=ALL9_OSCILLATORS
    )
    missing = [name for name in ("m2", "rs_eth", "dxy") if name not in extra_z]
    if missing:
        print(f"Missing required extras {missing} -- cannot run.")
        return

    from digiquant.strategies.sdca.optimize import SDCA_SHAPE_DEFAULTS

    weight_params = {
        "power_law_weight": ALL9_FLOOR_DIVERSIFIED_WEIGHTS.power_law,
        "sma_band_weight": ALL9_FLOOR_DIVERSIFIED_WEIGHTS.sma_band,
        "monthly_rsi_weight": ALL9_FLOOR_DIVERSIFIED_WEIGHTS.monthly_rsi,
        "m2_weight": ALL9_FLOOR_DIVERSIFIED_WEIGHTS.m2,
        "rs_eth_weight": ALL9_FLOOR_DIVERSIFIED_WEIGHTS.rs_eth,
        "dxy_weight": ALL9_FLOOR_DIVERSIFIED_WEIGHTS.dxy,
        "weekly_rsi_weight": ALL9_FLOOR_DIVERSIFIED_WEIGHTS.weekly_rsi,
        "weekly_macd_weight": ALL9_FLOOR_DIVERSIFIED_WEIGHTS.weekly_macd,
        "monthly_macd_weight": ALL9_FLOOR_DIVERSIFIED_WEIGHTS.monthly_macd,
    }
    trial = {**SDCA_SHAPE_DEFAULTS, **ALL9_WIDE_KNEE_SHAPE, **weight_params}

    import functools

    evaluator = functools.partial(evaluate_sdca_trial_curve_sim, oscillators=ALL9_OSCILLATORS)

    print("=== Stage 4: curve_simulator evaluator (3-fold walk-forward, all-9 floor-diversified candidate) ===")
    result_cs = run_sdca_walk_forward(
        dates,
        prices,
        [trial],
        rails_fitter=btc_power_law_rails_fitter,
        evaluator=evaluator,
        evaluator_label="curve_simulator/all9_floor_diversified_wide_knee",
        extra_z=extra_z,
    )
    print_wf_row("curve_simulator", result_cs)

    print("\n=== Comparison to validated baseline (RESEARCH_STATE.md) ===")
    print(
        f"{'validated baseline (defaults)':>40} | OOS  84.90 (curve_simulator) / 84.78 (nautilus)"
    )
    print(
        f"{'all9 floor-diversified wide-knee':>40} | OOS {result_cs.mean_oos_vs_flat_dca_pct:6.2f}"
    )
    print(
        "\nDiagnostic only. Not touching RESEARCH_STATE.md/settings.json -- "
        "report back for Chris's explicit accept/reject."
    )


if __name__ == "__main__":
    run()
