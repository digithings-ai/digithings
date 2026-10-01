#!/usr/bin/env python3
"""Gold (GLD) tiered curve search + walk-forward gate — METHOD.md step 5 (#4804).

Gold-local search on develop primitives (the research-branch robust
multi-window search + WIDE_KNEE grids were never ported to develop, and
develop's own ``search_curve`` maximizes total return — the known cycle-2
failure mode — so neither is used as-is):

- grid: own coarse tiered grid (~2k shapes, mid-tier keys included);
- windows: full history + each gate fold's IS window (fold geometry mirrors
  the gate defaults 3/0.2/0.25; all windows in-sample, OOS stays unseen);
- ranking: worst-case vs_flat_dca_pct across windows among feasible trials
  (the research objective, ported — not develop's max-return);
- gates: ``CurveOptimizeGates`` with ``require_2025_sells=False``
  (BTC-specific) at the call site; concentration bands are the fixed
  risk<25 / risk>70 cheap/rich zones;
- gate: ``run_sdca_walk_forward`` on the winner with per-fold
  generic_valuation rail refits (``fit_generic_valuation`` on each fold's IS
  window only — never a full-history fit inside the gate, #3173 rule).

KNOWN develop LIMIT (disclosed, same as promo-slice finding 3):
develop's ``shape_from_params`` drops mid-tier keys, so the gate evaluates
the winner's single-knee projection when the winner carries mid knees. The
sidecar records both the searched shape and the gated projection; a
single-knee grid variant is always in the running so at least one candidate
gates exactly.

Reads `.scratch/gold_seed.json` (frozen index) by default, or the seed file
given via ``--seed-path`` (v2 gate: ``gold_seed_v2deep.json`` /
``gold_seed_v2.json``); writes `.scratch/gold_curve_search.json`.
Research-only; touches nothing else.

Usage (gold worktree has no venv; research venv + src on PYTHONPATH):
    PYTHONPATH=digiquant/src <research-venv>/bin/python \\
        digiquant/scripts/run_gold_curve_search.py [--seed-path <seed.json>]
"""

from __future__ import annotations

import argparse
import itertools
import json
from collections.abc import Callable
from datetime import date
from pathlib import Path

import polars as pl

from digiquant.strategies.sdca.curve_optimize import (
    CurveOptimizeGates,
    score_shape_on_index,
)
from digiquant.strategies.sdca.curve_shape import SdcaCurveShape
from digiquant.strategies.sdca.curve_sim import evaluate_sdca_trial_curve_sim
from digiquant.strategies.sdca.generic_valuation import (
    GenericValuationRiskModel,
    fit_generic_valuation,
)
from digiquant.strategies.sdca.indicator_catalog import (
    WEIGHT_PARAM_BY_NAME,
    SdcaCompositeWeights,
    extra_z_vectors,
)
from digiquant.strategies.sdca.optimize import (
    load_sdca_extra_sources,
    run_sdca_walk_forward,
)
from digiquant.strategies.sdca.risk_model import RiskModel
from digiquant.strategies.sdca.rolling_z import RollingZRiskModel
from digiquant.strategies.sdca.walk_forward import (
    SdcaOptimizeObjective,
    make_walk_forward_folds,
    shape_from_params,
    window_slice,
)

DIGIQUANT_ROOT = Path(__file__).resolve().parents[1]
SEED_PATH = DIGIQUANT_ROOT / ".scratch" / "gold_seed.json"
DATA_PATH = DIGIQUANT_ROOT / "data" / "price-history" / "GLD-USD.csv"
OUT_PATH = DIGIQUANT_ROOT / ".scratch" / "gold_curve_search.json"

INITIAL_CASH = 10_000.0
# NOTE (#4804): seed vote params are derived from the seed file's weights at
# runtime (see main) so file and params cannot diverge — no hardcoded copy.

GRID = {
    "buy_max_rate": (10.0, 20.0, 35.0),
    "buy_knee_risk": (30.0, 45.0, 60.0),
    "sell_knee_risk": (50.0, 65.0, 80.0),
    "sell_max_rate": (10.0, 20.0, 30.0),
    "buy_curvature": (1.0, 1.5, 2.5),
    "sell_curvature": (1.0, 2.0),
    "buy_mid_knee_risk": (None, 15.0),
    "sell_mid_knee_risk": (None, 85.0),
}

GATES = CurveOptimizeGates(
    require_2025_sells=False,
    # Concentration bars OFF (research-branch precedent: they default to 0
    # there because they measure against fixed published knees, so a nonzero
    # floor rejects every wide-knee candidate outright -- verified 150/150
    # grid rejections on buys_outside_cheap_zone at develop's 0.99 default).
    # Selectivity comes from worst-case-vs-flat ranking + the walk-forward
    # DD cap instead.
    min_buy_frac_cheap=0.0,
    min_sell_frac_rich=0.0,
)


def gold_generic_rails_fitter(dates: list[date], prices: list[float]) -> RiskModel:
    """Per-fold generic_valuation refit (IS window only — #3173 rule)."""
    coeffs = fit_generic_valuation(
        pl.Series("date", dates, dtype=pl.Date),
        pl.Series("price", prices, dtype=pl.Float64),
        notes="gold walk-forward fold IS window; not full-history",
    )
    return GenericValuationRiskModel(coeffs)


def _make_bounded_lookback_rails_fitter(
    name: str, fit_lookback_days: int
) -> Callable[[list[date], list[float]], RiskModel]:
    """Inline rails variant (#4804 Task 3): same body as the gate fitter +
    the Task-2 ``fit_lookback_days`` only. Params match
    ``gold_rails_variants.json`` / ``VARIANT_SPECS`` exactly
    (form stays the ``log_quadratic`` default, no trend cap).
    Defined inline (not imported from ``run_gold_rails_variants``) because
    that module's top level mutates ``sys.path`` and back-imports this
    script's fitter — a circular import for no behavioral gain.
    """

    def _fitter(dates: list[date], prices: list[float]) -> RiskModel:
        coeffs = fit_generic_valuation(
            pl.Series("date", dates, dtype=pl.Date),
            pl.Series("price", prices, dtype=pl.Float64),
            fit_lookback_days=fit_lookback_days,
            notes=f"gold rails variant {name}; fold IS window only",
        )
        return GenericValuationRiskModel(coeffs)

    _fitter.__name__ = f"rails_fitter_{name}"
    return _fitter


def _make_rolling_z_rails_fitter(
    name: str, window: int, z: float
) -> Callable[[list[date], list[float]], RiskModel]:
    """Inline rolling-z rails variant (#4804 Task 4): same closure pattern as
    the bounded-lookback factory above, but constructing ``RollingZRiskModel``
    (trailing mean-reversion rails, no time-trend fit) with the v4 seed's
    anchor params (window 90, z 1.0). Defined inline for the same reason:
    no behavioral gain from sharing a module with ``run_gold_rails_variants``
    (whose factory only expresses generic_valuation kwargs).
    """

    def _fitter(dates: list[date], prices: list[float]) -> RiskModel:
        return RollingZRiskModel(
            pl.Series("date", dates, dtype=pl.Date),
            pl.Series("price", prices, dtype=pl.Float64),
            window=window,
            z=z,
        )

    _fitter.__name__ = f"rails_fitter_{name}"
    return _fitter


RAILS_FITTERS = {
    "default": gold_generic_rails_fitter,
    "quad_3y": _make_bounded_lookback_rails_fitter("quad_3y", 756),
    "quad_5y": _make_bounded_lookback_rails_fitter("quad_5y", 1260),
    "rolling90": _make_rolling_z_rails_fitter("rolling90", 90, 1.0),
}


def iter_grid() -> list[SdcaCurveShape]:
    shapes: list[SdcaCurveShape] = []
    keys = list(GRID)
    for combo in itertools.product(*(GRID[k] for k in keys)):
        params = dict(zip(keys, combo, strict=True))
        if not params["buy_knee_risk"] < params["sell_knee_risk"]:
            continue
        try:
            shapes.append(SdcaCurveShape(**params))
        except ValueError:
            continue
    return shapes


def main() -> None:
    parser = argparse.ArgumentParser(description="Gold GLD tiered curve search + gate")
    parser.add_argument("--seed-path", default=str(SEED_PATH))
    parser.add_argument(
        "--rails-variant",
        choices=sorted(RAILS_FITTERS),
        default="default",
    )
    parser.add_argument("--deployed-floor", type=float, default=None)
    parser.add_argument("--dd-cap", type=float, default=None)
    args = parser.parse_args()
    seed = json.loads(Path(args.seed_path).read_text())
    dates = [date.fromisoformat(d) for d in seed["dates"]]
    prices = list(seed["prices"])
    risk = seed["risk"]
    weights = SdcaCompositeWeights(**seed["weights"])
    seed_weight_params = {
        WEIGHT_PARAM_BY_NAME[name]: value for name, value in weights.model_dump().items()
    }
    print(f"gold seed: {dates[0]}..{dates[-1]} ({len(dates)} bars), weights={weights.model_dump()}")

    date_s = pl.Series("date", dates, dtype=pl.Date)
    price_s = pl.Series("price", prices, dtype=pl.Float64)
    risk_s = pl.Series("risk", risk, dtype=pl.Float64)

    folds, _holdout = make_walk_forward_folds(dates, n_folds=3, holdout_frac=0.2, oos_frac=0.25)
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

    shapes = iter_grid()
    print(f"grid: {len(shapes)} tiered shapes x {len(windows)} windows")
    best = None
    best_worst = float("-inf")
    evaluations = 0
    feasible_count = 0
    for shape in shapes:
        worst = float("inf")
        feasible_all = True
        for w_dates, w_prices, w_risk in windows:
            score = score_shape_on_index(
                w_dates, w_prices, w_risk, shape, INITIAL_CASH, gates=GATES
            )
            evaluations += 1
            feasible_all = feasible_all and score.feasible
            worst = min(worst, score.vs_flat_dca_pct)
        if feasible_all:
            feasible_count += 1
            if worst > best_worst:
                best_worst = worst
                best = shape
    if best is None:
        raise RuntimeError("no feasible gold shape under call-site gates")
    print(
        f"search: {evaluations} evaluations, {feasible_count} feasible, "
        f"winner worst_vs_flat={best_worst:.2f}% shape={best.model_dump()}"
    )

    # Gate the winner (develop's shape_from_params drops mid-tier keys —
    # the gate evaluates the single-knee projection; recorded, not hidden).
    winner_params = dict(seed_weight_params)
    for key, value in best.model_dump().items():
        if value is not None:
            winner_params[key] = value
    gated_shape = shape_from_params(winner_params)
    mid_dropped = gated_shape.model_dump() != best.model_dump()
    print(f"gate projection drops mid-tier keys: {mid_dropped}")

    sources = load_sdca_extra_sources(DATA_PATH.parent)
    extra_z = extra_z_vectors(date_s, price_s, weights, sources)
    print(f"rails-variant: {args.rails_variant}")
    objective = None
    if args.deployed_floor is not None or args.dd_cap is not None:
        objective = SdcaOptimizeObjective(
            capital_deployed_floor_pct=args.deployed_floor
            if args.deployed_floor is not None
            else 10.0,
            max_drawdown_cap_pct=args.dd_cap if args.dd_cap is not None else 50.0,
        )
    result = run_sdca_walk_forward(
        dates,
        prices,
        [winner_params],
        rails_fitter=RAILS_FITTERS[args.rails_variant],
        evaluator=evaluate_sdca_trial_curve_sim,
        evaluator_label="curve_simulator",
        extra_z=extra_z,
        objective=objective,
    )
    per_fold = [
        {
            "fold": fs.fold.fold,
            "oos_vs_flat_dca_pct": fs.out_of_sample.vs_flat_dca_pct,
            "oos_capital_deployed_pct": fs.out_of_sample.capital_deployed_pct,
            "oos_capital_deployed_peak_pct": fs.out_of_sample.capital_deployed_peak_pct,
            "max_drawdown_pct": fs.out_of_sample.max_drawdown_pct,
            "feasible": fs.feasible,
        }
        for fs in result.fold_scores
    ]
    print(
        f"gate: mean_oos_vs_flat={result.mean_oos_vs_flat_dca_pct:+.2f}% "
        f"beats_flat_dca_oos={result.beats_flat_dca_oos} "
        f"sensitivity_stable={result.sensitivity.stable} "
        f"(max_abs_delta={result.sensitivity.max_abs_delta_oos_pct:.2f})"
    )
    for f in per_fold:
        print(
            f"  fold {f['fold']}: oos_vs_flat={f['oos_vs_flat_dca_pct']:+.2f}% "
            f"max_dd={f['max_drawdown_pct']:.2f}% feasible={f['feasible']}"
        )

    OUT_PATH.write_text(
        json.dumps(
            {
                "weights": weights.model_dump(),
                "search": {
                    "num_shapes": len(shapes),
                    "num_evaluations": evaluations,
                    "num_feasible": feasible_count,
                    "worst_vs_flat_dca_pct": best_worst,
                    "shape": best.model_dump(),
                },
                "gate_projection_drops_mid_tier": mid_dropped,
                "gated_shape": gated_shape.model_dump(),
                "gate": {
                    "mean_oos_vs_flat_dca_pct": result.mean_oos_vs_flat_dca_pct,
                    "beats_flat_dca_oos": result.beats_flat_dca_oos,
                    "per_fold": per_fold,
                    "sensitivity_stable": result.sensitivity.stable,
                    "sensitivity_max_abs_delta": result.sensitivity.max_abs_delta_oos_pct,
                    # Gate-level worst-neighbor attribution (mean-OOS design; per-fold
                    # neighbor keys are explicitly out of scope).
                    "sensitivity_neighbor_count": result.sensitivity.neighbor_count,
                    "sensitivity_worst_neighbor_key": result.sensitivity.worst_neighbor_key,
                },
            },
            indent=2,
        )
    )
    print(f"wrote {OUT_PATH}")


if __name__ == "__main__":
    main()
