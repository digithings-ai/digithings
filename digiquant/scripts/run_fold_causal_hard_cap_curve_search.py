#!/usr/bin/env python3
"""Fold-causal Stage-3 index + hard-cap drawdown objective, combined.

Context (see project_digithings_sdca_strategy.md): two separate threads on
this project have each independently failed to fix fold 1's (COVID crash,
2019-07-01..2021-11-20) ~50-53% walk-forward OOS drawdown, but have never
been tried TOGETHER:

1. ``run_fold_drawdown_capped_curve_search.py`` (prior session): searched a
   fold-aware/hard-cap-drawdown curve objective, but against
   ``load_frozen_index()``'s LEAKY full-history-fit index. In-sample capping
   fold-1 drawdown at 25% did not transfer to OOS at all (41.63% OOS
   drawdown, capital_deployed=-529%, broken).
2. ``run_fold_causal_curve_search.py`` (this session): built a genuinely
   fold-causal index (each fold's rails fit on that fold's own IS window
   only, matching ``walk_forward.py``'s ``_score_fold()`` exactly), but
   searched it with the plain full-history ``risk_adjusted_return``
   objective. Did not rescue fold 1 either (57.83% in-sample fold1_dd on the
   winning shape, 53.29% real Stage-4 OOS drawdown).

Neither experiment tested the fold-causal index WITH the hard-cap objective.
It's possible the hard-cap search failed previously specifically because it
was fitting against a leaky signal that doesn't resemble what Stage 4 scores
fold 1 against -- i.e. the same root cause that explained why the plain
objective failed on the leaky index. This script combines both fixes: reuse
``StitchedFoldCausalRiskModel`` (fold-causal, no leakage) as the Stage-3
index, and score curve trials with the hard-cap objective (reject any trial
whose fold-1-window drawdown exceeds a cap, maximize return among survivors)
instead of plain risk_adjusted_return.

Diagnostic only. Does not touch settings.json or RESEARCH_STATE.md.

Usage:
    uv run python scripts/run_fold_causal_hard_cap_curve_search.py
"""

from __future__ import annotations

from datetime import date
from pathlib import Path

import numpy as np
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
from digiquant.strategies.sdca.walk_forward import make_walk_forward_folds, window_slice

DIGIQUANT_ROOT = Path(__file__).resolve().parents[1]
DEFAULT_CACHE_DIR = DIGIQUANT_ROOT / "data" / "price-history"

FROZEN_WEIGHTS = SdcaCompositeWeights(power_law=1.0, m2=0.5, dxy=0.5)
INITIAL_CASH = 1000.0
_DRAWDOWN_EPSILON = 0.5

FOLD1_START, FOLD1_END = date(2019, 7, 1), date(2021, 11, 20)
COVID_START, COVID_END = date(2020, 2, 1), date(2020, 4, 30)


class StitchedFoldCausalRiskModel:
    """A RiskModel that answers each date using only the fold model causal for it."""

    def __init__(self, dates: list[date], prices: list[float]) -> None:
        folds, holdout = make_walk_forward_folds(dates, n_folds=3, holdout_frac=0.2, oos_frac=0.25)
        self._folds = folds
        self._holdout_start = holdout[0]

        is0_d, is0_p = window_slice(dates, prices, folds[0].is_start, folds[0].is_end)
        self._model0 = btc_power_law_rails_fitter(is0_d, is0_p)
        is1_d, is1_p = window_slice(dates, prices, folds[1].is_start, folds[1].is_end)
        self._model1 = btc_power_law_rails_fitter(is1_d, is1_p)
        is2_d, is2_p = window_slice(dates, prices, folds[2].is_start, folds[2].is_end)
        self._model2 = btc_power_law_rails_fitter(is2_d, is2_p)
        full_d2, full_p2 = window_slice(dates, prices, dates[0], folds[2].oos_end)
        self._model_holdout = btc_power_law_rails_fitter(full_d2, full_p2)
        print(
            f"  fold-causal segments: seg0(<= {folds[0].oos_end}) fit on "
            f"{folds[0].is_start}..{folds[0].is_end} ({len(is0_d)}d); "
            f"seg1({folds[1].oos_start}..{folds[1].oos_end}) fit on "
            f"{folds[1].is_start}..{folds[1].is_end} ({len(is1_d)}d); "
            f"seg2({folds[2].oos_start}..{folds[2].oos_end}) fit on "
            f"{folds[2].is_start}..{folds[2].is_end} ({len(is2_d)}d); "
            f"holdout(> {folds[2].oos_end}) fit on {dates[0]}..{folds[2].oos_end} ({len(full_d2)}d)"
        )

    def rails(self, dates: pl.Series) -> pl.DataFrame:
        r0 = self._model0.rails(dates)
        r1 = self._model1.rails(dates)
        r2 = self._model2.rails(dates)
        rh = self._model_holdout.rails(dates)
        f0, f1, f2 = self._folds[0], self._folds[1], self._folds[2]
        mask0 = (dates <= f0.oos_end).to_numpy()
        mask1 = ((dates >= f1.oos_start) & (dates <= f1.oos_end)).to_numpy()
        mask2 = ((dates >= f2.oos_start) & (dates <= f2.oos_end)).to_numpy()
        out = {}
        for col in ("low", "median", "high"):
            out[col] = np.select(
                [mask0, mask1, mask2],
                [r0[col].to_numpy(), r1[col].to_numpy(), r2[col].to_numpy()],
                default=rh[col].to_numpy(),
            )
        return pl.DataFrame(out)


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

    trials = sample_wide_knee_curve_trials(n_random=3000)
    print(f"scoring {len(trials)} wide-knee trials against the fold-causal index "
          f"(hard-cap objective on fold1_dd)\n")

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

    print("=== hard-cap frontier: best total_return_pct among trials with fold1_dd <= cap (fold-causal index) ===")
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

    by_risk_adjusted = sorted(scored, key=lambda s: s["risk_adjusted_return"], reverse=True)
    print("\n=== top 5 by plain risk_adjusted_return (fold-causal index, for comparison) ===")
    for s in by_risk_adjusted[:5]:
        print(
            f"  ret={s['total_return_pct']:8.2f}%  full_dd={s['full_dd']:6.2f}%  "
            f"fold1_dd={s['fold1_dd']:6.2f}%  shape={s['shape'].model_dump()}"
        )

    if hard_cap_best is not None:
        winner = hard_cap_best["shape"]
        winner_params = winner.model_dump()
        print(f"\nUsing hard-cap-constrained winner (fold1_dd<=35%, fold-causal index) for Stage 4: {winner_params}")
        print(f"  full_dd={hard_cap_best['full_dd']:.2f}%  fold1_dd={hard_cap_best['fold1_dd']:.2f}%\n")
    else:
        winner = by_risk_adjusted[0]["shape"]
        winner_params = winner.model_dump()
        print(f"\nNo trial keeps fold1_dd<=35% on the fold-causal index -- falling back to risk_adjusted_return winner: {winner_params}")

    print("=== Stage 4: real walk-forward of the fold-causal + hard-cap winner ===\n")
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
            evaluator_label=f"{label}/fold_causal_hard_cap_curve",
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
