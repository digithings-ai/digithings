#!/usr/bin/env python3
"""Fold-causal index + soft swing penalty in the Stage-3 objective.

Context (project_digithings_sdca_strategy.md, drawdown-reduction detour, dead
ends #9-#10): hard constraints on capital-deployment swing (whether fold-1-only
or all-folds) both fail by relocating the instability — the optimizer picks a
shape that satisfies the swing cap on one fold by abandoning trading on
others, and OOS collapses to -55% mean. Hard constraints create knife-edge
feasible regions that force this relocation.

This script tests a different approach: instead of a hard constraint that
rejects trials exceeding a swing cap, fold capital-deployment swing into the
Stage-3 ranking objective as a soft regularization term. Use a modified
objective: `adjusted_return = total_return_pct - λ·fold1_swing_pct`, where λ
is a tunable penalty weight. Sweep λ (e.g., 0.0, 0.25, 0.5, 1.0, 1.5, 2.0)
to find the Pareto frontier of (swing, return) trade-offs. At each λ, pick
the best trial under the fold1_dd<=35% sanity check, then run its Stage 4
walk-forward. If a λ can be found where the adjusted objective produces a
Stage-4 winner that keeps fold-1 drawdown near the target AND preserves
capital deployment across all folds, that's the strongest candidate found to
date.

Diagnostic only. Does not touch settings.json or RESEARCH_STATE.md.

Usage:
    uv run python -m scripts.run_fold_causal_soft_swing_penalty
"""

from __future__ import annotations

from datetime import date
from pathlib import Path

import polars as pl

from digiquant.strategies.sdca.backtest import run_backtest
from digiquant.strategies.sdca.curve import AccumDistCurve
from digiquant.strategies.sdca.curve_optimize import (
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

DD_CAP = 35.0
PENALTY_WEIGHTS = (0.0, 0.25, 0.5, 1.0, 1.5, 2.0)


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
    fold1_net_deployed = fold1["net_deployed"].to_list() if fold1.height > 1 else [0.0]
    fold1_swing_pct = (max(fold1_net_deployed) - min(fold1_net_deployed)) / INITIAL_CASH * 100.0
    return {
        "shape": shape,
        "total_return_pct": report.total_return_pct,
        "full_dd": full_dd,
        "covid_dd": covid_dd,
        "fold1_dd": fold1_dd,
        "fold1_swing_pct": fold1_swing_pct,
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

    trials = sample_wide_knee_curve_trials(n_random=3000)
    print(f"scoring {len(trials)} wide-knee trials (fold1_dd cap={DD_CAP:.0f}%, sweeping soft swing-penalty weights)\n")

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

    under_dd_cap = [s for s in scored if s["fold1_dd"] <= DD_CAP]
    print(f"trials clearing fold1_dd<={DD_CAP:.0f}%: {len(under_dd_cap)} / {len(scored)}\n")

    print("=== frontier: best adjusted_return (with soft penalty) among trials under fold1_dd<=35% ===")
    winners = {}
    for penalty_weight in PENALTY_WEIGHTS:
        if not under_dd_cap:
            print(f"  λ={penalty_weight:5.2f}  n_trials=0")
            continue
        best = max(under_dd_cap, key=lambda s: s["total_return_pct"] - penalty_weight * s["fold1_swing_pct"])
        adjusted_ret = best["total_return_pct"] - penalty_weight * best["fold1_swing_pct"]
        print(
            f"  λ={penalty_weight:5.2f}  total_ret={best['total_return_pct']:8.2f}%  fold1_swing={best['fold1_swing_pct']:7.1f}%  "
            f"adjusted_ret={adjusted_ret:8.2f}%  full_dd={best['full_dd']:6.2f}%  fold1_dd={best['fold1_dd']:6.2f}%"
        )
        winners[penalty_weight] = best

    if not winners:
        print("No trials under dd cap -- aborting before Stage 4.")
        return

    best_penalty_weight = min(winners.keys(), key=lambda w: winners[w]["fold1_swing_pct"])
    winner = winners[best_penalty_weight]
    winner_params = winner["shape"].model_dump()
    print(
        f"\nUsing winner (λ={best_penalty_weight:.2f}, lowest swing) for Stage 4: {winner_params}\n"
        f"  total_return_pct={winner['total_return_pct']:.2f}%  fold1_swing_pct={winner['fold1_swing_pct']:.1f}%  "
        f"full_dd={winner['full_dd']:.2f}%  fold1_dd={winner['fold1_dd']:.2f}%\n"
    )

    print("=== Stage 4: real walk-forward of the soft-penalty fold-causal winner ===\n")
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
            evaluator_label=f"{label}/fold_causal_soft_swing_penalty",
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
