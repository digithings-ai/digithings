#!/usr/bin/env python3
"""Fold-causal index + hard-cap objective, with curvature capped.

Context (project_digithings_sdca_strategy.md): the prior experiment
(``run_fold_causal_hard_cap_curve_search.py``) combined the fold-causal
Stage-3 index with a hard-cap drawdown objective and, for the first time in
the whole project, got fold 1's real Stage-4 OOS drawdown under Chris's
<=30% target (22.69%). But the winning shape's ``buy_curvature=5.57`` (vs.
the published curve's 2.0) caused severe whipsaw: fold-1
``capital_deployed_pct`` swung to -317%, mean OOS went deeply negative, and
fold 0 broke too.

This script tests whether that whipsaw is specifically a curvature-extremity
artifact: rerun the identical fold-causal-index + hard-cap-objective search,
but with ``buy_curvature``/``sell_curvature`` bounded to [1.0, 2.5] in the
trial sampler (``WIDE_KNEE_SEARCH_BOUNDS`` defaults to [1.0, 6.0]) instead of
letting the hard-cap objective push curvature to an extreme to satisfy the
drawdown constraint. If a curvature-capped trial can still clear (or get
close to) the 30% fold-1 drawdown target without the capital-deployment
blowup, that isolates curvature-extremity as the actual failure mode. If
every capped trial fails to reach anywhere near 30%, that instead suggests
the earlier result's low fold-1 drawdown depended specifically on extreme
curvature (i.e. rapid, non-linear de-risking), not incidental to it.

Diagnostic only. Does not touch settings.json or RESEARCH_STATE.md.

Usage:
    uv run python scripts/run_fold_causal_hard_cap_curvature_capped.py
"""

from __future__ import annotations

from datetime import date
from pathlib import Path

import polars as pl

from digiquant.strategies.sdca.backtest import run_backtest
from digiquant.strategies.sdca.curve import AccumDistCurve
from digiquant.strategies.sdca.curve_optimize import (
    WIDE_KNEE_SEARCH_BOUNDS,
    SdcaCompositeWeights,
    SdcaCurveShape,
    sample_wide_knee_curve_trials,
)
from digiquant.strategies.sdca.curve_sim import evaluate_sdca_trial_curve_sim
from digiquant.strategies.sdca.indicator_catalog import build_extra_indicators
from digiquant.strategies.sdca.nautilus_evaluator import evaluate_sdca_trial_nautilus
from digiquant.strategies.sdca.optimize import (
    SDCA_SHAPE_DEFAULTS,
    btc_power_law_rails_fitter,
    drop_extras_missing_sources,
    load_sdca_extra_sources,
    load_sdca_extra_z,
    load_sdca_ohlcv,
    run_sdca_walk_forward,
)
from digiquant.strategies.sdca.risk_index import build_risk_index
from scripts.run_fold_causal_curve_search import StitchedFoldCausalRiskModel

DIGIQUANT_ROOT = Path(__file__).resolve().parents[1]
DEFAULT_CACHE_DIR = DIGIQUANT_ROOT / "data" / "price-history"

FROZEN_WEIGHTS = SdcaCompositeWeights(power_law=1.0, m2=0.5, dxy=0.5)
INITIAL_CASH = 1000.0
_DRAWDOWN_EPSILON = 0.5

FOLD1_START, FOLD1_END = date(2019, 7, 1), date(2021, 11, 20)
COVID_START, COVID_END = date(2020, 2, 1), date(2020, 4, 30)

CURVATURE_CAPPED_BOUNDS = {**WIDE_KNEE_SEARCH_BOUNDS, "buy_curvature": (1.0, 2.5), "sell_curvature": (1.0, 2.5)}


def _max_drawdown_pct(values: list[float]) -> float:
    peak = values[0]
    worst = 0.0
    for v in values:
        peak = max(peak, v)
        if peak > 0:
            worst = min(worst, (v - peak) / peak)
    return abs(worst) * 100.0


def score_trial(dates, prices, risk, shape: SdcaCurveShape) -> dict | None:
    try:
        report, frame = run_backtest(dates, prices, risk, AccumDistCurve(shape.to_nodes()), INITIAL_CASH)
    except Exception:
        return None
    full_dd = abs(report.dca_max_drawdown_pct) * 100.0
    covid = frame.filter((pl.col("date") >= COVID_START) & (pl.col("date") <= COVID_END))
    covid_dd = _max_drawdown_pct(covid["portfolio_value"].to_list()) if covid.height > 1 else 0.0
    fold1 = frame.filter((pl.col("date") >= FOLD1_START) & (pl.col("date") <= FOLD1_END))
    fold1_dd = _max_drawdown_pct(fold1["portfolio_value"].to_list()) if fold1.height > 1 else 0.0
    return {
        "shape": shape,
        "total_return_pct": report.total_return_pct,
        "full_dd": full_dd,
        "covid_dd": covid_dd,
        "fold1_dd": fold1_dd,
        "risk_adjusted_return": report.total_return_pct / max(full_dd, _DRAWDOWN_EPSILON),
    }


def run(cache_dir: Path = DEFAULT_CACHE_DIR) -> None:
    wf_dates, wf_prices = load_sdca_ohlcv(symbols=["BTC-USD"], data_path=None, data_dir=str(cache_dir))
    print(f"span: {wf_dates[0]}..{wf_dates[-1]} ({len(wf_dates)} days)")

    print("\nfitting stitched fold-causal risk model...")
    stitched = StitchedFoldCausalRiskModel(wf_dates, wf_prices)

    dates_s = pl.Series("date", wf_dates, dtype=pl.Date)
    price_s = pl.Series("price", wf_prices, dtype=pl.Float64)
    sources = load_sdca_extra_sources(cache_dir)
    resolved = drop_extras_missing_sources(FROZEN_WEIGHTS, sources)
    extras = build_extra_indicators(dates_s, price_s, resolved, sources)
    index = build_risk_index(
        dates_s, price_s, stitched, extra_indicators=extras or None, power_law_weight=resolved.power_law
    )
    trade_start = date(2018, 1, 1)
    window = index.filter(pl.col("date") >= trade_start)
    dates, prices, risk = window["date"], window["price"], window["risk"]
    print(f"fold-causal index span: {dates[0]}..{dates[-1]} ({len(dates)} days)\n")

    trials = sample_wide_knee_curve_trials(n_random=3000, bounds=CURVATURE_CAPPED_BOUNDS)
    print(
        f"scoring {len(trials)} curvature-capped ([1.0, 2.5]) wide-knee trials "
        f"against the fold-causal index (hard-cap objective on fold1_dd)\n"
    )

    scored = []
    for params in trials:
        try:
            shape = SdcaCurveShape(
                buy_max_rate=float(params["buy_max_rate"]),
                buy_knee_risk=float(params["buy_knee_risk"]),
                sell_knee_risk=float(params["sell_knee_risk"]),
                sell_max_rate=float(params["sell_max_rate"]),
                buy_curvature=float(params["buy_curvature"]),
                sell_curvature=float(params["sell_curvature"]),
            )
        except (KeyError, TypeError, ValueError):
            continue
        result = score_trial(dates, prices, risk, shape)
        if result is not None:
            scored.append(result)

    if not scored:
        print("no valid trials scored -- aborting")
        return

    print("=== hard-cap frontier: best total_return_pct among curvature-capped trials with fold1_dd <= cap ===")
    hard_cap_best = None
    for cap in (25.0, 30.0, 35.0, 40.0, 45.0, 50.0):
        under_cap = [s for s in scored if s["fold1_dd"] <= cap]
        if not under_cap:
            print(f"  cap={cap:5.1f}%  n_trials=0  (no trial keeps fold1_dd under this cap)")
            continue
        best = max(under_cap, key=lambda s: s["total_return_pct"])
        print(
            f"  cap={cap:5.1f}%  n_trials={len(under_cap):5d}  best_ret={best['total_return_pct']:8.2f}%  "
            f"full_dd={best['full_dd']:6.2f}%  fold1_dd={best['fold1_dd']:6.2f}%  shape={best['shape'].model_dump()}"
        )
        if cap <= 35.0 and hard_cap_best is None:
            hard_cap_best = best

    min_fold1_dd = min(s["fold1_dd"] for s in scored)
    print(f"\nMinimum achievable fold1_dd among ALL curvature-capped trials: {min_fold1_dd:.2f}%")

    if hard_cap_best is not None:
        winner = hard_cap_best["shape"]
        winner_params = winner.model_dump()
        print(f"\nUsing hard-cap-constrained winner (fold1_dd<=35%, curvature-capped) for Stage 4: {winner_params}")
        print(f"  full_dd={hard_cap_best['full_dd']:.2f}%  fold1_dd={hard_cap_best['fold1_dd']:.2f}%\n")
    else:
        winner = min(scored, key=lambda s: s["fold1_dd"])["shape"]
        winner_params = winner.model_dump()
        print(
            f"\nNo curvature-capped trial keeps fold1_dd<=35% -- falling back to the "
            f"lowest-fold1_dd trial found: {winner_params}"
        )

    print("=== Stage 4: real walk-forward of the curvature-capped fold-causal + hard-cap winner ===\n")
    extra_z = load_sdca_extra_z(wf_dates, wf_prices, data_path=None, data_dir=str(cache_dir))
    trial = {
        **SDCA_SHAPE_DEFAULTS,
        **{f"{k}": v for k, v in winner_params.items()},
        "power_law_weight": FROZEN_WEIGHTS.power_law,
        "m2_weight": FROZEN_WEIGHTS.m2,
        "dxy_weight": FROZEN_WEIGHTS.dxy,
    }

    for label, evaluator in (
        ("curve_simulator", evaluate_sdca_trial_curve_sim),
        ("nautilus", evaluate_sdca_trial_nautilus),
    ):
        result = run_sdca_walk_forward(
            wf_dates,
            wf_prices,
            [trial],
            rails_fitter=btc_power_law_rails_fitter,
            evaluator=evaluator,
            evaluator_label=f"{label}/fold_causal_hard_cap_curvature_capped",
            extra_z=extra_z,
        )
        holdout = result.holdout_metrics.vs_flat_dca_pct if result.holdout_metrics else float("nan")
        print(
            f"{label:>16} | IS {result.mean_is_vs_flat_dca_pct:7.2f} | OOS {result.mean_oos_vs_flat_dca_pct:7.2f} "
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
            f"max_abs_delta_oos={result.sensitivity.max_abs_delta_oos_pct:.2f}pp\n"
        )

    print(
        "Diagnostic only. Not touching RESEARCH_STATE.md/settings.json -- "
        "report back for Chris's explicit accept/reject."
    )


if __name__ == "__main__":
    run()
