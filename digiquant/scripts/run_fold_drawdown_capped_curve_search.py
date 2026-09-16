#!/usr/bin/env python3
"""Fold-aware curve-search objective: does penalizing COVID-window drawdown
specifically (not just full-history risk_adjusted_return) find a curve shape
whose walk-forward fold 1 (2019-07-01..2021-11-20, the COVID crash) is
finally feasible?

Context: every prior lead on this project (see
project_digithings_sdca_strategy.md) -- weight reweighting, indicator
diversification (including on-chain, including short trailing windows) --
converged to the SAME ~50-53% fold-1 COVID-crash drawdown regardless of
index composition. Reading ``curve_optimize.py``'s ``score_shape_on_index``
confirmed why: Stage 3's objective is a single full-history scalar
(``total_return_pct / max_drawdown_pct``) with no fold-awareness and no
per-crash-episode drawdown cap. A curve shape can look great on that
objective while still blowing through 50%+ drawdown during the COVID crash
specifically, as long as the REST of history's return/drawdown ratio is
good enough to dominate the average.

This script tests the concretely-identified next lead: re-score the SAME
wide-knee curve trial pool (``sample_wide_knee_curve_trials``, reused
as-is) against the VALIDATED baseline index (power_law=1.0/m2=0.5/dxy=0.5)
using a fold-capped objective --

    fold_capped_score = total_return_pct / max(full_history_dd, covid_window_dd, eps)

-- instead of ``risk_adjusted_return``. If a shape exists that scores well
under this objective AND survives a real Stage 4 walk-forward with fold 1
feasible, that is the first genuine sign the curve-search objective (not
index composition) was the actual lever. If nothing does, this closes the
"fold-aware objective" lead the same way the on-chain window sweep closed
the indicator-diversification lead.

Diagnostic only. Does not touch settings.json or RESEARCH_STATE.md.

Usage:
    uv run python scripts/run_fold_drawdown_capped_curve_search.py
"""

from __future__ import annotations

from datetime import date
from pathlib import Path

import polars as pl

from digiquant.strategies.sdca.backtest import run_backtest
from digiquant.strategies.sdca.curve_optimize import (
    AccumDistCurve,
    SdcaCompositeWeights,
    SdcaCurveShape,
    load_frozen_index,
    sample_wide_knee_curve_trials,
)
from digiquant.strategies.sdca.curve_sim import evaluate_sdca_trial_curve_sim
from digiquant.strategies.sdca.nautilus_evaluator import evaluate_sdca_trial_nautilus
from digiquant.strategies.sdca.optimize import (
    SDCA_SHAPE_DEFAULTS,
    btc_power_law_rails_fitter,
    load_sdca_extra_z,
    load_sdca_ohlcv,
    run_sdca_walk_forward,
)

DIGIQUANT_ROOT = Path(__file__).resolve().parents[1]
DEFAULT_CACHE_DIR = DIGIQUANT_ROOT / "data" / "price-history"

# Validated baseline weights (RESEARCH_STATE.md, +84.8-84.9% OOS).
FROZEN_WEIGHTS = SdcaCompositeWeights(power_law=1.0, m2=0.5, dxy=0.5)

# Fold 1's OOS window from the standing walk-forward split, and the COVID
# crash specifically inside it -- the sub-window every prior candidate blew
# through regardless of index composition.
FOLD1_START, FOLD1_END = date(2019, 7, 1), date(2021, 11, 20)
COVID_START, COVID_END = date(2020, 2, 1), date(2020, 4, 30)

_DRAWDOWN_EPSILON = 0.5
INITIAL_CASH = 1000.0


def _max_drawdown_pct(values: list[float]) -> float:
    peak = values[0]
    worst = 0.0
    for v in values:
        peak = max(peak, v)
        if peak > 0:
            worst = min(worst, (v - peak) / peak)
    return abs(worst) * 100.0


def score_trial(
    dates: pl.Series, prices: pl.Series, risk: pl.Series, shape: SdcaCurveShape
) -> dict | None:
    try:
        report, frame = run_backtest(dates, prices, risk, AccumDistCurve(shape.to_nodes()), INITIAL_CASH)
    except Exception:
        return None
    full_dd = abs(report.dca_max_drawdown_pct) * 100.0
    covid = frame.filter((pl.col("date") >= COVID_START) & (pl.col("date") <= COVID_END))
    covid_dd = _max_drawdown_pct(covid["portfolio_value"].to_list()) if covid.height > 1 else 0.0
    fold1 = frame.filter((pl.col("date") >= FOLD1_START) & (pl.col("date") <= FOLD1_END))
    fold1_dd = _max_drawdown_pct(fold1["portfolio_value"].to_list()) if fold1.height > 1 else 0.0
    capped_dd = max(full_dd, covid_dd, fold1_dd, _DRAWDOWN_EPSILON)
    return {
        "shape": shape,
        "total_return_pct": report.total_return_pct,
        "full_dd": full_dd,
        "covid_dd": covid_dd,
        "fold1_dd": fold1_dd,
        "fold_capped_score": report.total_return_pct / capped_dd,
        "risk_adjusted_return": report.total_return_pct / max(full_dd, _DRAWDOWN_EPSILON),
    }


def run(cache_dir: Path = DEFAULT_CACHE_DIR) -> None:
    dates, prices, risk, weights = load_frozen_index(cache_dir, weights=FROZEN_WEIGHTS)
    print(f"frozen weights: {weights.model_dump()}")
    print(f"index span: {dates[0]}..{dates[-1]} ({len(dates)} days)\n")

    trials = sample_wide_knee_curve_trials(n_random=3000)
    print(f"scoring {len(trials)} wide-knee trials against fold_capped_score = "
          f"total_return_pct / max(full_dd, covid_window_dd, fold1_window_dd, {_DRAWDOWN_EPSILON})\n")

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

    by_fold_capped = sorted(scored, key=lambda s: s["fold_capped_score"], reverse=True)
    by_risk_adjusted = sorted(scored, key=lambda s: s["risk_adjusted_return"], reverse=True)

    print("=== top 5 by fold_capped_score (new objective) ===")
    for s in by_fold_capped[:5]:
        print(
            f"  ret={s['total_return_pct']:8.2f}%  full_dd={s['full_dd']:6.2f}%  "
            f"covid_dd={s['covid_dd']:6.2f}%  fold1_dd={s['fold1_dd']:6.2f}%  "
            f"fold_capped_score={s['fold_capped_score']:.4f}  shape={s['shape'].model_dump()}"
        )
    print("\n=== top 5 by risk_adjusted_return (old, full-history-only objective, for comparison) ===")
    for s in by_risk_adjusted[:5]:
        print(
            f"  ret={s['total_return_pct']:8.2f}%  full_dd={s['full_dd']:6.2f}%  "
            f"covid_dd={s['covid_dd']:6.2f}%  fold1_dd={s['fold1_dd']:6.2f}%  "
            f"fold_capped_score={s['fold_capped_score']:.4f}  shape={s['shape'].model_dump()}"
        )

    print("\n=== hard-cap frontier: best total_return_pct among trials with fold1_dd <= cap ===")
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

    if hard_cap_best is not None:
        winner = hard_cap_best["shape"]
        winner_params = winner.model_dump()
        print(f"\nUsing hard-cap-constrained winner (fold1_dd<=35%) for Stage 4: {winner_params}")
        print(f"  full_dd={hard_cap_best['full_dd']:.2f}%  fold1_dd={hard_cap_best['fold1_dd']:.2f}%\n")
    else:
        winner = by_fold_capped[0]["shape"]
        winner_params = winner.model_dump()
        print(f"\nNo trial keeps fold1_dd<=35% -- falling back to fold_capped_score winner: {winner_params}")
        print(
            f"  full_dd={by_fold_capped[0]['full_dd']:.2f}%  covid_dd={by_fold_capped[0]['covid_dd']:.2f}%  "
            f"fold1_dd={by_fold_capped[0]['fold1_dd']:.2f}%\n"
        )

    print("=== Stage 4: walk-forward the fold_capped_score winner ===\n")
    wf_dates, wf_prices = load_sdca_ohlcv(symbols=["BTC-USD"], data_path=None, data_dir=str(cache_dir))
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
            evaluator_label=f"{label}/fold_drawdown_capped_curve",
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
