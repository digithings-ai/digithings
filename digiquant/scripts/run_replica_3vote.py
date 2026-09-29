#!/usr/bin/env python3
"""3-vote replica rerun: match production's DEFAULT toggles (Sharpe OFF).

Production default = Tail Curvature + Cost Basis + Onchain (Sharpe unchecked).
The 4-vote comparison ran all four; this reruns the replica side with three
votes, same 181k-eval tiered robust search budget, same raw + gated legs.
Our side is reused from `.scratch/replica_comparison.json` (deterministic
search; already recorded) -- only the replica leg is recomputed.

Sidecar: `.scratch/replica_3vote.json` (untracked). Research-only.

Usage:
    uv run python scripts/run_replica_3vote.py
"""

from __future__ import annotations

import json
from pathlib import Path

import polars as pl
import run_replica_comparison as rc

from digiquant.strategies.sdca.composite_risk import (
    IndicatorWeight,
    compute_composite_risk,
)
from digiquant.strategies.sdca.curve_optimize import (
    _MID_TIER_KEYS,
    WIDE_KNEE_TIERED_COARSE_GRID,
    WIDE_KNEE_TIERED_SEARCH_BOUNDS,
)
from digiquant.strategies.sdca.curve_optimize_feasibility import (
    search_wide_knee_curve_multi_window_robust,
)
from digiquant.strategies.sdca.optimize import (
    load_sdca_extra_sources,
    load_sdca_ohlcv,
    run_sdca_walk_forward,
)
from digiquant.strategies.sdca.signals_replica import (
    cost_basis_ratio_z,
    onchain_composite_z,
    sharpe_z,
    tail_curvature_z,
)
from digiquant.strategies.sdca.walk_forward import (
    make_walk_forward_folds,
    window_slice,
)

DIGIQUANT_ROOT = Path(__file__).resolve().parents[1]
OUT_PATH = DIGIQUANT_ROOT / ".scratch" / "replica_3vote.json"

VOTES_3 = ("tail_curvature", "cost_basis", "onchain")


def main() -> None:
    prior = json.loads((DIGIQUANT_ROOT / ".scratch" / "replica_comparison.json").read_text())
    dates, prices = load_sdca_ohlcv(
        symbols=["BTC-USD"], data_path=rc.DEFAULT_DATA_PATH, data_dir=None
    )
    date_s = pl.Series("date", dates, dtype=pl.Date)
    price_s = pl.Series("price", prices, dtype=pl.Float64)
    print(f"BTC-USD {dates[0]}..{dates[-1]} ({len(dates)} daily bars)")

    sources = load_sdca_extra_sources(rc.DEFAULT_DATA_PATH.parent)
    votes = {
        "tail_curvature": tail_curvature_z(price_s),
        # Sharpe deliberately OFF -- production default toggle is unchecked.
        "cost_basis": cost_basis_ratio_z(
            date_s, sources.onchain_mvrv_dates, sources.onchain_mvrv_values
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
    frame = compute_composite_risk(
        [IndicatorWeight(name=n, z=votes[n], weight=1.0) for n in VOTES_3]
    )
    replica_risk = frame["risk"].to_list()
    print(
        f"3-vote replica composite (no sharpe): "
        f"{sum(1 for v in replica_risk if v is not None)}/{len(replica_risk)} non-null"
    )

    folds, _holdout = make_walk_forward_folds(dates, n_folds=3, holdout_frac=0.2, oos_frac=0.25)
    risk_s = pl.Series("risk", replica_risk, dtype=pl.Float64)
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
    print("searching 3-vote replica index (same budget)...")
    search = search_wide_knee_curve_multi_window_robust(
        windows,
        initial_cash=rc.INITIAL_CASH,
        bounds=WIDE_KNEE_TIERED_SEARCH_BOUNDS,
        grid=WIDE_KNEE_TIERED_COARSE_GRID,
        extra_keys=_MID_TIER_KEYS,
    )
    print(
        f"  3-vote winner: worst_vs_flat={search.best.worst_vs_flat_dca_pct:.2f}% "
        f"evals={search.num_evaluations} shape={search.best.shape.model_dump()}"
    )
    assert search.num_evaluations == prior["replica_search"]["num_evaluations"], (
        "search budget diverged from the 4-vote run -- not like-for-like"
    )

    print("raw leg (full-history in-sample):")
    raw = rc.raw_score("replica-3vote", dates, prices, replica_risk, search.best.shape)

    print("gated leg (walk-forward OOS vs flat, same folds):")
    result = run_sdca_walk_forward(
        dates,
        prices,
        [rc.shape_params(search.best.shape)],
        rails_fitter=rc.cheap_rails_stand_in,
        evaluator=rc.make_frozen_risk_evaluator(dates, replica_risk),
        evaluator_label="frozen_replica_3vote_risk",
        extra_z=None,
        fold_weighting="duration",
    )
    oos = result.mean_oos_vs_flat_dca_pct_duration_weighted
    print(
        f"  replica-3vote duration-OOS={oos:+.2f}% "
        f"folds={[round(fs.out_of_sample.vs_flat_dca_pct, 2) for fs in result.fold_scores]}"
    )

    print("attribution leg (drop-one of 3 votes, fixed winner shape, full history):")
    attribution = {}
    for vote in VOTES_3:
        kept = [IndicatorWeight(name=n, z=votes[n], weight=1.0) for n in VOTES_3 if n != vote]
        dropped = rc.raw_score(
            f"replica-3vote w/o {vote}",
            dates,
            prices,
            compute_composite_risk(kept)["risk"].to_list(),
            search.best.shape,
        )
        attribution[vote] = dropped["vs_flat_dca_pct"] - raw["vs_flat_dca_pct"]
        print(f"    w/o {vote}: delta_vs_flat={attribution[vote]:+.2f}pp")

    sharpe_added_votes = dict(votes)
    sharpe_added_votes["sharpe"] = sharpe_z(price_s)
    from digiquant.strategies.sdca.signals_replica import build_replica_composite

    full4 = rc.raw_score(
        "replica-4vote (reference)",
        dates,
        prices,
        build_replica_composite(sharpe_added_votes)["risk"].to_list(),
        search.best.shape,
    )
    print(
        f"  4-vote composite on 3-vote winner shape: vs_flat={full4['vs_flat_dca_pct']:+.2f}% "
        f"(vs 3-vote {raw['vs_flat_dca_pct']:+.2f}%)"
    )

    OUT_PATH.write_text(
        json.dumps(
            {
                "votes": list(VOTES_3),
                "num_evaluations": search.num_evaluations,
                "worst_vs_flat_dca_pct": search.best.worst_vs_flat_dca_pct,
                "shape": search.best.shape.model_dump(),
                "raw": raw,
                "gated_oos_duration_weighted": oos,
                "attribution_drop_one": attribution,
                "four_vote_reference_raw": full4,
                "ours_reused": {
                    "gated_oos_duration_weighted": prior["our_gated_oos_duration_weighted"],
                    "raw": prior["our_raw"],
                },
            },
            indent=2,
        )
    )
    print(f"wrote {OUT_PATH}")


if __name__ == "__main__":
    main()
