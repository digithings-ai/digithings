#!/usr/bin/env python3
"""Gold (GLD) v3-winner holdout validation — scored ONCE (#4804).

Evaluates the honest-v3 gate winner (single-knee projection 35/45/50/30/1.0/2.0,
weights valuation 1.0 / m2 0.5 / uup 0.5) on the never-scored holdout tail
(2022-05-12..2026-09-29). Shape and weights are READ from
``.scratch/gold_curve_search_honest_v3.json`` — never re-derived, no search,
no gate rerun.

RESERVE (binding): this script spends the plan's single holdout-scoring
reserve. Do NOT run it a second time for any reason — a bad output, crash
mid-write, or wrong params means STOP with NEEDS_CONTEXT for a controller
ruling, not a re-run. The output (``.scratch/gold_holdout_v3.json``) is
untracked; only this script is committed.

Vehicle: ``_holdout_metrics`` (optimize.py) — fits rails on the searchable
span and scores the holdout slice in one evaluator call, with no gate-fold
re-evaluation and no sensitivity fan-out. ``run_sdca_walk_forward`` would redo
the whole gate (folds + ~49 sensitivity neighbors) for the same single
holdout record.
Fitter: ``gold_generic_rails_fitter`` IMPORTED from the gate script
(``run_gold_curve_search.py``) — that module's top level is side-effect-free
(pure imports, constants, defs; ``main()`` under ``__main__`` guard), so no
local copy.

Usage (from the repo root of the gold worktree), exactly once:
    PYTHONPATH=digiquant/src .venv/bin/python \\
        digiquant/scripts/run_gold_holdout_validation.py

Writes ``.scratch/gold_holdout_v3.json`` (untracked). Research-only.
"""

from __future__ import annotations

import json
import sys
import time
from datetime import date
from pathlib import Path

import polars as pl

from digiquant.strategies.sdca.curve_sim import evaluate_sdca_trial_curve_sim
from digiquant.strategies.sdca.indicator_catalog import (
    WEIGHT_PARAM_BY_NAME,
    SdcaCompositeWeights,
    extra_z_vectors,
)
from digiquant.strategies.sdca.optimize import (
    SDCA_SHAPE_DEFAULTS,
    _holdout_metrics,
    load_sdca_extra_sources,
)
from digiquant.strategies.sdca.walk_forward import (
    SdcaOptimizeObjective,
    is_feasible,
    make_walk_forward_folds,
)

sys.path.insert(0, str(Path(__file__).resolve().parent))
from run_gold_curve_search import gold_generic_rails_fitter

DIGIQUANT_ROOT = Path(__file__).resolve().parents[1]
SEED_PATH = DIGIQUANT_ROOT / ".scratch" / "gold_seed_v3.json"
HONEST_PATH = DIGIQUANT_ROOT / ".scratch" / "gold_curve_search_honest_v3.json"
DATA_PATH = DIGIQUANT_ROOT / "data" / "price-history" / "GLD-USD.csv"
OUT_PATH = DIGIQUANT_ROOT / ".scratch" / "gold_holdout_v3.json"

EXPECTED_HOLDOUT = (date(2022, 5, 12), date(2026, 9, 29))
EXPECTED_RAILS_FIT = (date(2004, 11, 18), date(2022, 5, 11))


def main() -> None:
    t0 = time.monotonic()
    seed = json.loads(SEED_PATH.read_text())
    honest = json.loads(HONEST_PATH.read_text())
    dates = [date.fromisoformat(d) for d in seed["dates"]]
    prices = [float(p) for p in seed["prices"]]
    weights = SdcaCompositeWeights(**honest["weights"])
    shape = dict(honest["gated_shape"])
    print(f"v3 seed: {dates[0]}..{dates[-1]} ({len(dates)} bars)")
    print(f"v3 winner (gated projection): {shape}, weights={weights.model_dump()}")

    folds, holdout = make_walk_forward_folds(dates, n_folds=3, holdout_frac=0.2, oos_frac=0.25)
    if tuple(holdout) != EXPECTED_HOLDOUT:
        print("HOLDOUT GEOMETRY MISMATCH — refusing to score on wrong windows", file=sys.stderr)
        print(f"  expected holdout: {EXPECTED_HOLDOUT[0]}..{EXPECTED_HOLDOUT[1]}", file=sys.stderr)
        print(f"  recomputed holdout: {holdout[0]}..{holdout[1]}", file=sys.stderr)
        for fold in folds:
            print(
                f"  recomputed fold {fold.fold}: IS {fold.is_start}..{fold.is_end} "
                f"OOS {fold.oos_start}..{fold.oos_end}",
                file=sys.stderr,
            )
        raise SystemExit(1)
    print(f"holdout asserted: {holdout[0]}..{holdout[1]}")

    rails_fit_window = (dates[0], folds[-1].oos_end)
    if tuple(rails_fit_window) != EXPECTED_RAILS_FIT:
        print("RAILS-FIT WINDOW MISMATCH — refusing to fit on wrong span", file=sys.stderr)
        print(
            f"  expected rails fit: {EXPECTED_RAILS_FIT[0]}..{EXPECTED_RAILS_FIT[1]}",
            file=sys.stderr,
        )
        print(
            f"  recomputed rails fit: {rails_fit_window[0]}..{rails_fit_window[1]}",
            file=sys.stderr,
        )
        raise SystemExit(1)
    print(
        f"rails fit window asserted (pre-holdout only): {rails_fit_window[0]}..{rails_fit_window[1]}"
    )

    date_s = pl.Series("date", dates, dtype=pl.Date)
    price_s = pl.Series("price", prices, dtype=pl.Float64)
    sources = load_sdca_extra_sources(DATA_PATH.parent)
    extra_z = extra_z_vectors(date_s, price_s, weights, sources)
    print(f"extra_z legs: {sorted(extra_z)}")

    seed_weight_params = {
        WEIGHT_PARAM_BY_NAME[name]: value for name, value in weights.model_dump().items()
    }
    winner_params = {
        **SDCA_SHAPE_DEFAULTS,
        **seed_weight_params,
        **{k: v for k, v in shape.items() if v is not None},
    }
    # THE single holdout scoring of this plan — no other evaluator call on this slice.
    metrics = _holdout_metrics(
        winner_params,
        dates,
        prices,
        folds,
        holdout,
        gold_generic_rails_fitter,
        evaluate_sdca_trial_curve_sim,
        extra_z,
    )
    objective = SdcaOptimizeObjective()
    feasible = is_feasible(metrics, objective)
    print(
        f"holdout: vs_flat={metrics.vs_flat_dca_pct:+.2f}% "
        f"vs_lump={metrics.vs_lump_pct:+.2f}% "
        f"deployed_net={metrics.capital_deployed_pct:.2f}% "
        f"deployed_peak={metrics.capital_deployed_peak_pct:.2f}% "
        f"max_dd={metrics.max_drawdown_pct:.2f}% feasible={feasible}"
    )
    print(
        "objective: default SdcaOptimizeObjective "
        f"(floor {objective.capital_deployed_floor_pct} on capital_deployed_peak_pct, "
        f"cap {objective.max_drawdown_cap_pct} on max_drawdown_pct)"
    )

    OUT_PATH.write_text(
        json.dumps(
            {
                "weights": weights.model_dump(),
                "shape": shape,
                "rails_fit_window": [str(rails_fit_window[0]), str(rails_fit_window[1])],
                "holdout_window": [str(holdout[0]), str(holdout[1])],
                "metrics": {
                    "vs_flat_dca_pct": metrics.vs_flat_dca_pct,
                    "vs_lump_pct": metrics.vs_lump_pct,
                    "capital_deployed_pct": metrics.capital_deployed_pct,
                    "capital_deployed_peak_pct": metrics.capital_deployed_peak_pct,
                    "max_drawdown_pct": metrics.max_drawdown_pct,
                },
                "feasible": feasible,
                "holdout_scored_once": True,
            },
            indent=2,
        )
    )
    print(f"wrote {OUT_PATH} in {time.monotonic() - t0:.0f}s")


if __name__ == "__main__":
    main()
