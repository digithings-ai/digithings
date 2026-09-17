#!/usr/bin/env python3
"""Stage 3 (curve refit) + Stage 4 (OOS walk-forward) on the composite
rolling-renormalization winner from ``run_baseline_composite_smoothing_search.py``.

That script found, in-sample only, that turning on ``compute_composite_risk``'s
``rolling_window=365`` knob (currently off/``None`` in every existing script)
scores +54.98 higher on the combined cycle-overlap objective than the
validated baseline's un-renormalized composite (137.66 -> 192.64), the
largest in-sample delta found across any lead this project has tried so far
-- larger than the joint-period-retuning winner's +9.29 (dead end #15,
rejected). ``smoothing_window`` did not help on top of it (every smoothed
variant scored lower than its un-smoothed counterpart), so this candidate
only turns on rolling re-normalization, not smoothing.

Everything needed is already exposed natively: ``build_risk_index`` (and
therefore ``evaluate_sdca_trial_curve_sim``) already forward
``composite_rolling_window``/``composite_rolling_min_samples`` to
``compute_composite_risk`` -- no plumbing gap this time, just bind via
``functools.partial`` per each function's own docstring.

Runs curve_simulator only (the standard protocol's fast go/no-go gate) --
Nautilus is a follow-up only if this clears the bar.

Per the standing gate: diagnostic only, does not touch settings.json or
RESEARCH_STATE.md. Report the table back to Chris for explicit accept/reject.

Usage:
    uv run python -m scripts.run_composite_rolling365_stage34
"""

from __future__ import annotations

import functools
from pathlib import Path

import polars as pl

from digiquant.strategies.sdca.curve_optimize import search_wide_knee_curve
from digiquant.strategies.sdca.curve_sim import evaluate_sdca_trial_curve_sim
from digiquant.strategies.sdca.indicator_catalog import SdcaCompositeWeights
from digiquant.strategies.sdca.optimize import (
    SDCA_SHAPE_DEFAULTS,
    btc_power_law_rails_fitter,
    load_sdca_extra_z,
    load_sdca_ohlcv,
    run_sdca_walk_forward,
)
from digiquant.strategies.sdca.risk_index import build_risk_index

DIGIQUANT_ROOT = Path(__file__).resolve().parents[1]
DEFAULT_CACHE_DIR = DIGIQUANT_ROOT / "data" / "price-history"

# Composite smoothing search winner (run_baseline_composite_smoothing_search.py, +54.98 in-sample).
COMPOSITE_ROLLING_WINDOW = 365
COMPOSITE_ROLLING_MIN_SAMPLES = None  # defaults to max(20, window // 2) inside compute_composite_risk

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

    from digiquant.strategies.sdca.btc_power_law import BtcPowerLawRiskModel, load_coefficients

    risk_model = BtcPowerLawRiskModel(load_coefficients())

    print(
        f"frozen knob: composite_rolling_window={COMPOSITE_ROLLING_WINDOW} "
        f"(weights/periods at code defaults, power_law=1.0 m2=0.5 dxy=0.5)\n"
    )

    extra_z = load_sdca_extra_z(dates, prices, data_path=None, data_dir=str(cache_dir))
    extra_indicators = [
        {"name": "m2", "z": extra_z["m2"], "weight": BASELINE_WEIGHTS.m2},
        {"name": "dxy", "z": extra_z["dxy"], "weight": BASELINE_WEIGHTS.dxy},
    ]
    from digiquant.strategies.sdca.composite_risk import IndicatorWeight

    index = build_risk_index(
        date_s,
        price_s,
        risk_model,
        extra_indicators=[
            IndicatorWeight(name=i["name"], z=pl.Series("z", i["z"], dtype=pl.Float64), weight=i["weight"])
            for i in extra_indicators
        ],
        power_law_weight=BASELINE_WEIGHTS.power_law,
        composite_rolling_window=COMPOSITE_ROLLING_WINDOW,
        composite_rolling_min_samples=COMPOSITE_ROLLING_MIN_SAMPLES,
    )
    risk_s = index["risk"]

    print("=== Stage 3: wide-knee curve search against the rolling-renormalized index ===")
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
        f"max_drawdown_pct={curve_result.best.max_drawdown_pct:.2f}\n"
    )

    # --- Stage 4: OOS walk-forward on the frozen (weights + rolling knob + curve) trial ---
    weight_params = {"power_law_weight": 1.0, "m2_weight": 0.5, "dxy_weight": 0.5}
    trial = {**SDCA_SHAPE_DEFAULTS, **shape_params, **weight_params}

    evaluator = functools.partial(
        evaluate_sdca_trial_curve_sim,
        composite_rolling_window=COMPOSITE_ROLLING_WINDOW,
        composite_rolling_min_samples=COMPOSITE_ROLLING_MIN_SAMPLES,
    )

    print("=== Stage 4: curve_simulator evaluator (3-fold walk-forward, frozen candidate) ===")
    result_cs = run_sdca_walk_forward(
        dates,
        prices,
        [trial],
        rails_fitter=btc_power_law_rails_fitter,
        evaluator=evaluator,
        evaluator_label="curve_simulator/composite_rolling365",
        extra_z=extra_z,
    )
    print_wf_row("curve_simulator", result_cs)

    print("\n=== Comparison to validated baseline (RESEARCH_STATE.md) ===")
    print(
        f"{'validated baseline (defaults)':>40} | OOS  84.90 (curve_simulator) / 84.78 (nautilus)"
    )
    print(
        f"{'composite rolling_window=365 (curve_sim)':>40} | OOS {result_cs.mean_oos_vs_flat_dca_pct:6.2f}"
    )
    print(
        "\nDiagnostic only. Not touching RESEARCH_STATE.md/settings.json -- "
        "report back for Chris's explicit accept/reject."
    )


if __name__ == "__main__":
    run()
