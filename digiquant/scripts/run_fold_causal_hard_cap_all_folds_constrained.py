#!/usr/bin/env python3
"""Fold-causal index + hard-cap drawdown + all-folds swing constraint.

Context (project_digithings_sdca_strategy.md, drawdown-reduction detour, dead
end #9): constraining fold-1's capital-deployment swing in isolation
(alongside the 35% fold1_dd hard-cap) does kill the whipsaw (fold-1 OOS
capital_deployed goes from -317%/-377% to +20.43%), but the optimizer just
relocates the damage — folds 0 and 2 both come back feasible=False with
capital_deployed near zero, mean OOS collapses to -55.45%, and returns are
even worse than dead ends #7/#8.

This script tests whether the problem is the isolated fold-1 constraint:
extend the swing hard constraint to ALL THREE folds (0, 1, 2), not just fold
1, alongside the existing 35% fold1_dd cap. If no curve shape can satisfy
*all* constraints simultaneously (fold1_dd<=35%, fold0_swing+fold1_swing+fold2_swing
all within a per-fold cap), that's strong evidence the constraints are
fundamentally contradictory and no curve-shape search can rescue the goal.
If a shape *can* satisfy all constraints, that's the strongest candidate found
to date — a curve that keeps all folds trading stably while hitting the
fold-1 drawdown target.

Diagnostic only. Does not touch settings.json or RESEARCH_STATE.md.

Usage:
    uv run python -m scripts.run_fold_causal_hard_cap_all_folds_constrained
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

FOLD0_START, FOLD0_END = date(2018, 1, 1), date(2019, 6, 30)
FOLD1_START, FOLD1_END = date(2019, 7, 1), date(2021, 11, 20)
FOLD2_START, FOLD2_END = date(2021, 11, 21), date(2024, 4, 12)

DD_CAP = 35.0
SWING_CAPS = (75.0, 100.0, 150.0, 200.0, 300.0, None)


def _max_drawdown_pct(values: list[float]) -> float:
    peak = values[0]
    worst = 0.0
    for v in values:
        peak = max(peak, v)
        if peak > 0:
            worst = min(worst, (v - peak) / peak)
    return abs(worst) * 100.0


def _fold_swing_pct(frame, start: date, end: date) -> float:
    fold = frame.filter((pl.col("date") >= start) & (pl.col("date") <= end))
    if fold.height <= 1:
        return 0.0
    net_deployed = fold["net_deployed"].to_list()
    return (max(net_deployed) - min(net_deployed)) / INITIAL_CASH * 100.0


def score_trial(dates, prices, risk, shape: SdcaCurveShape) -> dict | None:
    try:
        report, frame = run_backtest(dates, prices, risk, AccumDistCurve(shape.to_nodes()), INITIAL_CASH)
    except Exception:
        return None
    full_dd = abs(report.dca_max_drawdown_pct) * 100.0
    fold0 = frame.filter((pl.col("date") >= FOLD0_START) & (pl.col("date") <= FOLD0_END))
    fold0_dd = _max_drawdown_pct(fold0["portfolio_value"].to_list()) if fold0.height > 1 else 0.0
    fold0_swing = _fold_swing_pct(frame, FOLD0_START, FOLD0_END)
    fold1 = frame.filter((pl.col("date") >= FOLD1_START) & (pl.col("date") <= FOLD1_END))
    fold1_dd = _max_drawdown_pct(fold1["portfolio_value"].to_list()) if fold1.height > 1 else 0.0
    fold1_swing = _fold_swing_pct(frame, FOLD1_START, FOLD1_END)
    fold2 = frame.filter((pl.col("date") >= FOLD2_START) & (pl.col("date") <= FOLD2_END))
    fold2_dd = _max_drawdown_pct(fold2["portfolio_value"].to_list()) if fold2.height > 1 else 0.0
    fold2_swing = _fold_swing_pct(frame, FOLD2_START, FOLD2_END)
    return {
        "shape": shape,
        "total_return_pct": report.total_return_pct,
        "full_dd": full_dd,
        "fold0_dd": fold0_dd,
        "fold0_swing": fold0_swing,
        "fold1_dd": fold1_dd,
        "fold1_swing": fold1_swing,
        "fold2_dd": fold2_dd,
        "fold2_swing": fold2_swing,
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
    print(
        f"scoring {len(trials)} wide-knee trials (fold1_dd cap={DD_CAP:.0f}%, "
        f"sweeping per-fold swing caps on all 3 folds)\n"
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

    under_dd_cap = [s for s in scored if s["fold1_dd"] <= DD_CAP]
    print(f"trials clearing fold1_dd<={DD_CAP:.0f}%: {len(under_dd_cap)} / {len(scored)}")
    if under_dd_cap:
        fold0_swings = sorted(abs(s["fold0_swing"]) for s in under_dd_cap)
        fold1_swings = sorted(s["fold1_swing"] for s in under_dd_cap)
        fold2_swings = sorted(abs(s["fold2_swing"]) for s in under_dd_cap)
        print(
            f"  fold0_swing_pct: min={fold0_swings[0]:.1f}  median={fold0_swings[len(fold0_swings)//2]:.1f}  max={fold0_swings[-1]:.1f}"
        )
        print(
            f"  fold1_swing_pct: min={fold1_swings[0]:.1f}  median={fold1_swings[len(fold1_swings)//2]:.1f}  max={fold1_swings[-1]:.1f}"
        )
        print(
            f"  fold2_swing_pct: min={fold2_swings[0]:.1f}  median={fold2_swings[len(fold2_swings)//2]:.1f}  max={fold2_swings[-1]:.1f}\n"
        )

    print("=== frontier: best total_return_pct among trials with fold1_dd<=35% AND all folds' swing<=cap ===")
    winner = None
    winner_cap_label = None
    for swing_cap in SWING_CAPS:
        if swing_cap is None:
            survivors = under_dd_cap
            label = "uncapped"
        else:
            survivors = [
                s
                for s in under_dd_cap
                if abs(s["fold0_swing"]) <= swing_cap and abs(s["fold1_swing"]) <= swing_cap and abs(s["fold2_swing"]) <= swing_cap
            ]
            label = f"{swing_cap:.0f}%"
        if not survivors:
            print(f"  swing_cap={label:>8}  n_trials=0")
            continue
        best = max(survivors, key=lambda s: s["total_return_pct"])
        print(
            f"  swing_cap={label:>8}  n_trials={len(survivors):5d}  best_ret={best['total_return_pct']:8.2f}%  "
            f"full_dd={best['full_dd']:6.2f}%  fold1_dd={best['fold1_dd']:6.2f}%  "
            f"fold0_sw={abs(best['fold0_swing']):7.1f}%  fold1_sw={best['fold1_swing']:7.1f}%  fold2_sw={abs(best['fold2_swing']):7.1f}%  "
            f"shape={best['shape'].model_dump()}"
        )
        if winner is None and swing_cap is not None and swing_cap <= 150.0:
            winner = best
            winner_cap_label = label

    if winner is None:
        print("\nNo trial clears both fold1_dd<=35% and all-folds swing<=150% -- falling back to lowest-total-swing survivor under the dd cap")
        if under_dd_cap:
            winner = min(
                under_dd_cap, key=lambda s: abs(s["fold0_swing"]) + abs(s["fold1_swing"]) + abs(s["fold2_swing"])
            )
            winner_cap_label = "fallback (min total swing)"
        else:
            print("No trial even clears the drawdown cap -- aborting before Stage 4.")
            return

    winner_params = winner["shape"].model_dump()
    print(f"\nUsing winner (swing_cap={winner_cap_label}) for Stage 4: {winner_params}")
    print(
        f"  full_dd={winner['full_dd']:.2f}%  fold1_dd={winner['fold1_dd']:.2f}%  "
        f"fold0_swing={abs(winner['fold0_swing']):.1f}%  fold1_swing={winner['fold1_swing']:.1f}%  fold2_swing={abs(winner['fold2_swing']):.1f}%\n"
    )

    print("=== Stage 4: real walk-forward of the all-folds-constrained fold-causal + hard-cap winner ===\n")
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
            evaluator_label=f"{label}/fold_causal_hard_cap_all_folds_constrained",
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
