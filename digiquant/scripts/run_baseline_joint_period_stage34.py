#!/usr/bin/env python3
"""Stage 3 (curve refit) + Stage 4 (OOS walk-forward) on the joint period
re-tuning winner from ``run_baseline_joint_period_search.py``.

That script found, in-sample only, that jointly searching the validated
baseline's (``power_law=1.0, m2=0.5, dxy=0.5``) three construction periods
together -- rather than leaving them at whatever the code defaults happened
to be -- scores +9.29 higher on the combined cycle-overlap objective:
``trend_window=500, m2_roc_days=270, m2_window=150, dxy_window=60`` vs. the
defaults' ``trend_window=180, m2_roc_days=365, m2_window=90, dxy_window=90``.

Plumbing note: ``load_sdca_extra_z``/``build_extra_indicators`` only expose a
single shared ``window`` kwarg for BOTH ``m2_liquidity_z`` and ``dxy_z`` --
no path exists to give them independent windows. This script sidesteps that
by computing the m2/dxy z-series directly (same pattern already used by
``run_fear_greed_stage2_reweight.py`` for fear_greed) and splicing them into
the extra_z dict handed to ``run_sdca_walk_forward``, which accepts a raw
``extra_z`` mapping regardless of how it was built.

Separately, ``evaluate_sdca_trial_curve_sim``/``build_risk_index`` support an
``oscillators`` override for ``power_law_trend_window``, but the evaluator
never forwarded it (only ``composite_rolling_window`` was exposed for
``functools.partial`` binding). Added an ``oscillators`` kwarg to
``evaluate_sdca_trial_curve_sim`` (mirroring the existing
``composite_rolling_window`` pattern) so the winning ``trend_window=500`` can
be tested through walk-forward too, not just through the one-shot
``load_frozen_index``/Stage-1 path.

Runs curve_simulator only (the standard protocol's fast go/no-go gate) --
Nautilus is a follow-up only if this clears the bar.

Per the standing gate: diagnostic only, does not touch settings.json or
RESEARCH_STATE.md. Report the table back to Chris for explicit accept/reject.

Usage:
    uv run python -m scripts.run_baseline_joint_period_stage34
"""

from __future__ import annotations

import functools
from pathlib import Path

import polars as pl

from digiquant.strategies.sdca.curve_optimize import search_wide_knee_curve
from digiquant.strategies.sdca.curve_sim import evaluate_sdca_trial_curve_sim
from digiquant.strategies.sdca.indicator_catalog import (
    SdcaCompositeWeights,
    dxy_z,
    m2_liquidity_z,
)
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

# Joint period-search winner (run_baseline_joint_period_search.py, +9.29 in-sample).
TREND_WINDOW = 500
M2_ROC_DAYS = 270
M2_WINDOW = 150
DXY_WINDOW = 60

BASELINE_WEIGHTS = SdcaCompositeWeights(power_law=1.0, m2=0.5, dxy=0.5)
FROZEN_OSCILLATORS = SdcaOscillatorSpec(power_law_trend_window=TREND_WINDOW)


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

    m2_z = m2_liquidity_z(
        date_s, sources.m2_dates, sources.m2_values, roc_days=M2_ROC_DAYS, window=M2_WINDOW
    ).to_list()
    dxy_z_series = dxy_z(date_s, sources.dxy_dates, sources.dxy_values, window=DXY_WINDOW).to_list()

    print(
        f"frozen periods: trend_window={TREND_WINDOW} m2_roc_days={M2_ROC_DAYS} "
        f"m2_window={M2_WINDOW} dxy_window={DXY_WINDOW}\n"
    )

    # --- Stage 3: curve refit against the frozen (retuned-period) index ---
    from digiquant.strategies.sdca.btc_power_law import BtcPowerLawRiskModel, load_coefficients

    risk_model = BtcPowerLawRiskModel(load_coefficients())
    rails = risk_model.rails(date_s)
    power_law_z = power_law_confluence_z(
        date_s, price_s, rails["low"], rails["median"], rails["high"], trend_window=TREND_WINDOW
    ).to_list()
    risk = risk_from_weighted_z(dates, power_law_z, {"m2": m2_z, "dxy": dxy_z_series}, BASELINE_WEIGHTS)
    risk_s = pl.Series("risk", risk, dtype=pl.Float64)

    print("=== Stage 3: wide-knee curve search against the retuned-period index ===")
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

    # --- Stage 4: OOS walk-forward on the frozen (weights + periods + curve) trial ---
    extra_z = load_sdca_extra_z(
        dates, prices, data_path=None, data_dir=str(cache_dir), oscillators=FROZEN_OSCILLATORS
    )
    extra_z["m2"] = m2_z
    extra_z["dxy"] = dxy_z_series

    weight_params = {"power_law_weight": 1.0, "m2_weight": 0.5, "dxy_weight": 0.5}
    trial = {**SDCA_SHAPE_DEFAULTS, **shape_params, **weight_params}

    evaluator = functools.partial(evaluate_sdca_trial_curve_sim, oscillators=FROZEN_OSCILLATORS)

    print("=== Stage 4: curve_simulator evaluator (3-fold walk-forward, frozen candidate) ===")
    result_cs = run_sdca_walk_forward(
        dates,
        prices,
        [trial],
        rails_fitter=btc_power_law_rails_fitter,
        evaluator=evaluator,
        evaluator_label="curve_simulator/baseline_joint_period_retune",
        extra_z=extra_z,
    )
    print_wf_row("curve_simulator", result_cs)

    print("\n=== Comparison to validated baseline (RESEARCH_STATE.md) ===")
    print(
        f"{'validated baseline (defaults)':>40} | OOS  84.90 (curve_simulator) / 84.78 (nautilus)"
    )
    print(
        f"{'joint period retune (curve_sim)':>40} | OOS {result_cs.mean_oos_vs_flat_dca_pct:6.2f}"
    )
    print(
        "\nDiagnostic only. Not touching RESEARCH_STATE.md/settings.json -- "
        "report back for Chris's explicit accept/reject."
    )


if __name__ == "__main__":
    run()
