#!/usr/bin/env python3
"""Signals-replica challenger comparison (2026-09-29-signals-replica-challenger spec §5).

Builds the production replica composite (``signals_replica``) and our live
index on IDENTICAL dates/prices/cash, runs the SAME tiered robust
curve-search budget on both frozen risk series, then reports:

- raw (production-style): full-history in-sample winner scored vs lump sum,
  vs flat DCA, max DDs, deployment;
- gated (our protocol): walk-forward OOS vs flat DCA on the same folds for
  both winners. ``beats_production_oos`` = ours minus replica on
  duration-weighted OOS vs-flat (> 0 clears);
- resilience read-out: drop-one-vote sensitivity on the replica composite
  (fixed winner shape) vs drop-one-indicator on our index, to direct the
  "harden our index" step.

Fairness notes (spec §4): production's default 21-node curve is unknown, so
no invented curve is claimed as parity — both indexes get the identical
search budget and both winners are compared raw AND gated. The replica risk
series is fully causal (no rails); ours here is the Task-7 frozen index
(full-history rails, same series the cycle curve-search uses). The gated leg
for ours additionally uses per-fold rail refit (cycle protocol); the replica
leg uses a frozen-risk evaluator (no rails exist to refit) with a cheap
stand-in rails fitter whose output the evaluator ignores.

Research-only. Writes nothing to settings.json / presets.json.
Result sidecar: ``.scratch/replica_comparison.json`` (untracked).

Usage:
    uv run python scripts/run_replica_comparison.py
"""

from __future__ import annotations

import functools
import json
from collections.abc import Sequence
from datetime import date
from pathlib import Path

import polars as pl
import run_aggregate_reweight_full17_fixed_index as reweight

from digiquant.strategies.sdca.backtest import run_backtest
from digiquant.strategies.sdca.composite_risk import (
    IndicatorWeight,
    compute_composite_risk,
)
from digiquant.strategies.sdca.curve import AccumDistCurve
from digiquant.strategies.sdca.curve_optimize import (
    _MID_TIER_KEYS,
    WIDE_KNEE_TIERED_COARSE_GRID,
    WIDE_KNEE_TIERED_SEARCH_BOUNDS,
    published_indicator_weights,
)
from digiquant.strategies.sdca.curve_optimize_feasibility import (
    search_wide_knee_curve_multi_window_robust,
)
from digiquant.strategies.sdca.curve_shape import SdcaCurveShape
from digiquant.strategies.sdca.curve_sim import evaluate_sdca_trial_curve_sim
from digiquant.strategies.sdca.indicator_catalog import SdcaCompositeWeights
from digiquant.strategies.sdca.optimize import (
    btc_power_law_rails_fitter,
    load_sdca_extra_sources,
    load_sdca_ohlcv,
    run_sdca_walk_forward,
)
from digiquant.strategies.sdca.price_oscillators import SdcaOscillatorSpec
from digiquant.strategies.sdca.risk_model import RiskModel
from digiquant.strategies.sdca.rolling_z import RollingZRiskModel
from digiquant.strategies.sdca.signals_replica import (
    REPLICA_VOTE_NAMES,
    build_replica_composite,
    cost_basis_ratio_z,
    onchain_composite_z,
    sharpe_z,
    tail_curvature_z,
)
from digiquant.strategies.sdca.stage_a import risk_from_weighted_z
from digiquant.strategies.sdca.two_stage import freeze_weight_params
from digiquant.strategies.sdca.walk_forward import (
    SdcaTrialMetrics,
    make_walk_forward_folds,
    window_slice,
)

DIGIQUANT_ROOT = Path(__file__).resolve().parents[1]
DEFAULT_DATA_PATH = DIGIQUANT_ROOT / "data" / "price-history" / "BTC-USD.csv"
OUT_PATH = DIGIQUANT_ROOT / ".scratch" / "replica_comparison.json"

INITIAL_CASH = 10_000.0
GATE_OSCILLATORS = SdcaOscillatorSpec()


def shape_params(shape: SdcaCurveShape) -> dict[str, float | int | str]:
    """Curve-shape fields for a trial dict (drop None mid-tier keys)."""
    return {key: value for key, value in shape.model_dump().items() if value is not None}


def params_for(weights: SdcaCompositeWeights, shape: SdcaCurveShape) -> dict:
    trial: dict[str, float | int | str] = dict(freeze_weight_params(weights))
    trial.update(shape_params(shape))
    return trial


def make_frozen_risk_evaluator(all_dates: list[date], all_risk: list[float | None]):
    """Trial evaluator that scores a precomputed risk series (replica: no rails).

    Ignores ``risk_model``/weights — the risk series is fixed, only the curve
    ``shape`` varies. Maps ``run_backtest`` onto ``SdcaTrialMetrics`` with the
    same convention as ``evaluate_sdca_trial_curve_sim``.
    """
    index = {d: i for i, d in enumerate(all_dates)}

    def _eval(
        dates: Sequence[date],
        prices: Sequence[float],
        risk_model: RiskModel,
        shape: SdcaCurveShape,
        power_law_weight: float,
        extra_indicators: Sequence[IndicatorWeight] | None = None,
    ) -> SdcaTrialMetrics:
        risk = pl.Series(
            "risk",
            [all_risk[index[d]] for d in dates],
            dtype=pl.Float64,
        )
        report, _frame = run_backtest(
            pl.Series("date", list(dates), dtype=pl.Date),
            pl.Series("price", list(prices), dtype=pl.Float64),
            risk,
            AccumDistCurve(shape.to_nodes()),
            INITIAL_CASH,
        )
        return SdcaTrialMetrics(
            vs_flat_dca_pct=report.vs_flat_dca_pct,
            vs_lump_pct=report.vs_lump_pct,
            capital_deployed_pct=report.capital_deployed_pct,
            capital_deployed_peak_pct=report.capital_deployed_peak_pct,
            max_drawdown_pct=abs(report.dca_max_drawdown_pct) * 100.0,
        )

    return _eval


def cheap_rails_stand_in(dates: Sequence[date], prices: Sequence[float]) -> RiskModel:
    """Stand-in rails fitter for the frozen-risk leg (output ignored).

    Walk-forward still calls the fitter per fold; QuantReg refits would be
    pure waste since the frozen evaluator never touches the model.
    """
    return RollingZRiskModel(
        pl.Series("date", list(dates), dtype=pl.Date),
        pl.Series("price", list(prices), dtype=pl.Float64),
    )


def raw_score(
    label: str,
    dates: list[date],
    prices: list[float],
    risk: list[float | None],
    shape: SdcaCurveShape,
) -> dict:
    """Production-style raw read-out: full-history winner vs lump / flat / DDs."""
    report, _frame = run_backtest(
        pl.Series("date", dates, dtype=pl.Date),
        pl.Series("price", prices, dtype=pl.Float64),
        pl.Series("risk", risk, dtype=pl.Float64),
        AccumDistCurve(shape.to_nodes()),
        INITIAL_CASH,
    )
    out = {
        "vs_lump_pct": report.vs_lump_pct,
        "vs_flat_dca_pct": report.vs_flat_dca_pct,
        "dca_max_drawdown_pct": report.dca_max_drawdown_pct * 100.0,
        "buy_hold_max_drawdown_pct": report.buy_hold_max_drawdown_pct * 100.0,
        "capital_deployed_pct": report.capital_deployed_pct,
        "capital_deployed_peak_pct": report.capital_deployed_peak_pct,
        "buy_days": report.buy_days,
        "sell_days": report.sell_days,
        "no_trade_days": report.no_trade_days,
    }
    print(
        f"  raw {label}: vs_lump={out['vs_lump_pct']:+.2f}% "
        f"vs_flat={out['vs_flat_dca_pct']:+.2f}% "
        f"dd={out['dca_max_drawdown_pct']:.2f}% "
        f"(buy&hold {out['buy_hold_max_drawdown_pct']:.2f}%) "
        f"deployed_peak={out['capital_deployed_peak_pct']:.1f}% "
        f"buy/sell/flat={out['buy_days']}/{out['sell_days']}/{out['no_trade_days']}"
    )
    return out


def main() -> None:
    dates, prices = load_sdca_ohlcv(symbols=["BTC-USD"], data_path=DEFAULT_DATA_PATH, data_dir=None)
    date_s = pl.Series("date", dates, dtype=pl.Date)
    price_s = pl.Series("price", prices, dtype=pl.Float64)
    print(f"BTC-USD {dates[0]}..{dates[-1]} ({len(dates)} daily bars)")

    # -- Replica composite on identical data --
    sources = load_sdca_extra_sources(DEFAULT_DATA_PATH.parent)
    votes = {
        "tail_curvature": tail_curvature_z(price_s),
        "sharpe": sharpe_z(price_s),
        "cost_basis": cost_basis_ratio_z(
            date_s,
            sources.onchain_mvrv_dates,
            sources.onchain_mvrv_values,
        ),
        "onchain": onchain_composite_z(
            date_s,
            {
                "mvrv": (sources.onchain_mvrv_dates, sources.onchain_mvrv_values),
                "asopr": (sources.onchain_asopr_dates, sources.onchain_asopr_values),
                "puell": (sources.onchain_puell_dates, sources.onchain_puell_values),
                "rhodl": (sources.onchain_rhodl_dates, sources.onchain_rhodl_values),
            },
        ),
    }
    replica_frame = build_replica_composite(votes)
    replica_risk = replica_frame["risk"].to_list()
    n_null = sum(1 for v in replica_risk if v is None)
    print(f"replica composite built (4 equal votes, {n_null} null warmup rows)")

    # -- Our index: Task-7 frozen index at live weights (cycle curve-search input) --
    fdates, power_law_z, extra_z, _long_w, _medium_w = reweight.load_inputs()
    assert fdates == dates, "reweight.load_inputs dates differ from OHLCV dates"
    live_weights = published_indicator_weights()
    our_risk = risk_from_weighted_z(dates, power_law_z, extra_z, live_weights)
    print(f"our index built (live weights: {live_weights.model_dump()})")

    # -- Identical fold geometry + search windows per index --
    folds, _holdout = make_walk_forward_folds(dates, n_folds=3, holdout_frac=0.2, oos_frac=0.25)

    def search_windows(risk: list[float | None]):
        risk_s = pl.Series("risk", risk, dtype=pl.Float64)
        windows = [(date_s, price_s, risk_s)]
        for fold in folds:
            i0 = dates.index(fold.is_start)
            i1 = dates.index(fold.is_end)
            w_dates, w_prices = window_slice(dates, prices, fold.is_start, fold.is_end)
            windows.append(
                (
                    pl.Series("date", w_dates, dtype=pl.Date),
                    pl.Series("price", w_prices, dtype=pl.Float64),
                    risk_s.slice(i0, i1 - i0 + 1),
                )
            )
        return windows

    print("searching replica index (same budget as ours)...")
    replica_search = search_wide_knee_curve_multi_window_robust(
        search_windows(replica_risk),
        initial_cash=INITIAL_CASH,
        bounds=WIDE_KNEE_TIERED_SEARCH_BOUNDS,
        grid=WIDE_KNEE_TIERED_COARSE_GRID,
        extra_keys=_MID_TIER_KEYS,
    )
    print(
        f"  replica winner: worst_vs_flat={replica_search.best.worst_vs_flat_dca_pct:.2f}% "
        f"evals={replica_search.num_evaluations} shape={replica_search.best.shape.model_dump()}"
    )

    print("searching our index (same budget as replica)...")
    our_search = search_wide_knee_curve_multi_window_robust(
        search_windows(our_risk),
        initial_cash=INITIAL_CASH,
        bounds=WIDE_KNEE_TIERED_SEARCH_BOUNDS,
        grid=WIDE_KNEE_TIERED_COARSE_GRID,
        extra_keys=_MID_TIER_KEYS,
    )
    print(
        f"  our winner: worst_vs_flat={our_search.best.worst_vs_flat_dca_pct:.2f}% "
        f"evals={our_search.num_evaluations} shape={our_search.best.shape.model_dump()}"
    )
    assert replica_search.num_evaluations == our_search.num_evaluations, (
        "search budgets diverged -- comparison is not like-for-like"
    )

    # -- Raw leg (production-style, full-history IS) --
    print("raw leg (full-history in-sample, production-style):")
    replica_raw = raw_score("replica", dates, prices, replica_risk, replica_search.best.shape)
    our_raw = raw_score("ours", dates, prices, our_risk, our_search.best.shape)

    # -- Gated leg (walk-forward OOS vs flat, same folds) --
    print("gated leg (walk-forward OOS vs flat DCA, same folds):")
    evaluator = functools.partial(evaluate_sdca_trial_curve_sim, oscillators=GATE_OSCILLATORS)
    our_trial = params_for(live_weights, our_search.best.shape)
    our_result = run_sdca_walk_forward(
        dates,
        prices,
        [our_trial],
        rails_fitter=btc_power_law_rails_fitter,
        evaluator=evaluator,
        evaluator_label="curve_simulator",
        extra_z=extra_z,
        fold_weighting="duration",
    )
    replica_trial = shape_params(replica_search.best.shape)
    replica_result = run_sdca_walk_forward(
        dates,
        prices,
        [replica_trial],
        rails_fitter=cheap_rails_stand_in,
        evaluator=make_frozen_risk_evaluator(dates, replica_risk),
        evaluator_label="frozen_replica_risk",
        extra_z=None,
        fold_weighting="duration",
    )
    our_oos = our_result.mean_oos_vs_flat_dca_pct_duration_weighted
    replica_oos = replica_result.mean_oos_vs_flat_dca_pct_duration_weighted
    beats_production_oos = bool(our_oos - replica_oos > 0)
    print(
        f"  ours duration-OOS={our_oos:+.2f}% "
        f"folds={[round(fs.out_of_sample.vs_flat_dca_pct, 2) for fs in our_result.fold_scores]}"
    )
    print(
        f"  replica duration-OOS={replica_oos:+.2f}% "
        f"folds={[round(fs.out_of_sample.vs_flat_dca_pct, 2) for fs in replica_result.fold_scores]}"
    )
    print(f"  beats_production_oos={beats_production_oos} (delta={our_oos - replica_oos:+.2f}pp)")

    # -- Resilience read-out: drop-one attribution, fixed winner shapes --
    print("attribution leg (drop-one vote/indicator, fixed winner shapes, full history):")
    attribution: dict = {"replica_drop_one_vote": {}, "ours_drop_one_indicator": {}}
    for vote in REPLICA_VOTE_NAMES:
        kept = [
            IndicatorWeight(name=n, z=votes[n], weight=1.0) for n in REPLICA_VOTE_NAMES if n != vote
        ]
        frame = compute_composite_risk(kept)
        dropped = raw_score(
            f"replica w/o {vote}",
            dates,
            prices,
            frame["risk"].to_list(),
            replica_search.best.shape,
        )
        attribution["replica_drop_one_vote"][vote] = (
            dropped["vs_flat_dca_pct"] - replica_raw["vs_flat_dca_pct"]
        )
        print(f"    w/o {vote}: delta_vs_flat={attribution['replica_drop_one_vote'][vote]:+.2f}pp")
    enabled = {k: v for k, v in live_weights.model_dump().items() if v > 0}
    for name in enabled:
        payload = dict(live_weights.model_dump())
        payload[name] = 0.0
        dropped_risk = risk_from_weighted_z(
            dates, power_law_z, extra_z, SdcaCompositeWeights(**payload)
        )
        dropped = raw_score(f"ours w/o {name}", dates, prices, dropped_risk, our_search.best.shape)
        attribution["ours_drop_one_indicator"][name] = (
            dropped["vs_flat_dca_pct"] - our_raw["vs_flat_dca_pct"]
        )
        print(
            f"    w/o {name}: delta_vs_flat={attribution['ours_drop_one_indicator'][name]:+.2f}pp"
        )

    OUT_PATH.parent.mkdir(parents=True, exist_ok=True)
    OUT_PATH.write_text(
        json.dumps(
            {
                "beats_production_oos": beats_production_oos,
                "delta_oos_pp": our_oos - replica_oos,
                "replica_search": {
                    "num_evaluations": replica_search.num_evaluations,
                    "worst_vs_flat_dca_pct": replica_search.best.worst_vs_flat_dca_pct,
                    "shape": replica_search.best.shape.model_dump(),
                },
                "our_search": {
                    "num_evaluations": our_search.num_evaluations,
                    "worst_vs_flat_dca_pct": our_search.best.worst_vs_flat_dca_pct,
                    "shape": our_search.best.shape.model_dump(),
                },
                "replica_raw": replica_raw,
                "our_raw": our_raw,
                "replica_gated_oos_duration_weighted": replica_oos,
                "our_gated_oos_duration_weighted": our_oos,
                "attribution": attribution,
            },
            indent=2,
        )
    )
    print(f"wrote {OUT_PATH}")
    print(f"beats_production_oos={beats_production_oos}")


if __name__ == "__main__":
    main()
