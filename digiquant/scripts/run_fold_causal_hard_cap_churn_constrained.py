#!/usr/bin/env python3
"""Fold-causal index + hard-cap drawdown objective, PLUS a churn constraint.

Context (project_digithings_sdca_strategy.md, drawdown-reduction detour, dead
ends #7 and #8): the fold-causal-index + hard-cap-drawdown-objective search
is the only approach in the whole project that gets fold 1's real Stage-4 OOS
drawdown under Chris's <=30% target. But every curve shape found that way
whipsaws violently in fold 1 -- capital_deployed_pct swings to -317% (dead
end #7, buy_curvature=5.57) or -377% (dead end #8, curvature capped to
[1.0, 2.5], which made the whipsaw WORSE, not better -- falsifying the
"curvature extremity is the cause" hypothesis).

This script tests next-lead candidates (a)+(c) together: instead of only
constraining fold-1 drawdown, ALSO constrain fold-1 capital-deployment churn
directly in the Stage-3 objective -- reject any trial whose in-sample
fold-1-window net-deployed-capital swing (max - min, as % of initial cash)
exceeds a cap, in addition to the existing fold1_dd cap, then maximize
total_return_pct among survivors. If no curve shape can satisfy both
constraints simultaneously, that's strong evidence the ~30% drawdown target
and stable capital deployment are in direct, irreducible tension under this
curve-shape family (as increasingly suspected). If a shape *can* satisfy
both, that's the strongest drawdown-detour candidate found to date and
worth a full Stage 4 validation.

Diagnostic only. Does not touch settings.json or RESEARCH_STATE.md.

Usage:
    uv run python -m scripts.run_fold_causal_hard_cap_churn_constrained
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
SWING_CAPS = (50.0, 75.0, 100.0, 150.0, 200.0, 300.0, None)


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
    print(f"scoring {len(trials)} wide-knee trials (fold1_dd cap={DD_CAP:.0f}%, sweeping fold1 churn caps)\n")

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
    print(f"trials clearing fold1_dd<={DD_CAP:.0f}%: {len(under_dd_cap)} / {len(scored)}")
    if under_dd_cap:
        swings = sorted(s["fold1_swing_pct"] for s in under_dd_cap)
        print(f"  fold1_swing_pct among these: min={swings[0]:.1f}  median={swings[len(swings)//2]:.1f}  max={swings[-1]:.1f}\n")

    print("=== frontier: best total_return_pct among trials with fold1_dd<=35% AND fold1_swing_pct<=cap ===")
    winner = None
    winner_cap_label = None
    for swing_cap in SWING_CAPS:
        if swing_cap is None:
            survivors = under_dd_cap
            label = "uncapped"
        else:
            survivors = [s for s in under_dd_cap if abs(s["fold1_swing_pct"]) <= swing_cap]
            label = f"{swing_cap:.0f}%"
        if not survivors:
            print(f"  swing_cap={label:>8}  n_trials=0")
            continue
        best = max(survivors, key=lambda s: s["total_return_pct"])
        print(
            f"  swing_cap={label:>8}  n_trials={len(survivors):5d}  best_ret={best['total_return_pct']:8.2f}%  "
            f"full_dd={best['full_dd']:6.2f}%  fold1_dd={best['fold1_dd']:6.2f}%  fold1_swing={best['fold1_swing_pct']:8.1f}%  "
            f"shape={best['shape'].model_dump()}"
        )
        if winner is None and swing_cap is not None and swing_cap <= 150.0:
            winner = best
            winner_cap_label = label

    if winner is None:
        print("\nNo trial clears both fold1_dd<=35% and any tested swing cap<=150% -- falling back to lowest-swing survivor under the dd cap")
        if under_dd_cap:
            winner = min(under_dd_cap, key=lambda s: abs(s["fold1_swing_pct"]))
            winner_cap_label = "fallback (min swing)"
        else:
            print("No trial even clears the drawdown cap -- aborting before Stage 4.")
            return

    winner_params = winner["shape"].model_dump()
    print(f"\nUsing winner (swing_cap={winner_cap_label}) for Stage 4: {winner_params}")
    print(f"  full_dd={winner['full_dd']:.2f}%  fold1_dd={winner['fold1_dd']:.2f}%  fold1_swing_pct={winner['fold1_swing_pct']:.1f}%\n")

    print("=== Stage 4: real walk-forward of the churn-constrained fold-causal + hard-cap winner ===\n")
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
            evaluator_label=f"{label}/fold_causal_hard_cap_churn_constrained",
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
