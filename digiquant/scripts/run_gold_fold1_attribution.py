#!/usr/bin/env python3
"""Gold (GLD) fold-1 attribution — diagnostic, no gate changes (#4804).

Recomputes the v1 walk-forward fold dates, runs index-level leg diagnostics
over fold-1 OOS and four calendar subperiods, and replays the v1 winner shape
on fold-1 with drop-one-leg variants through ``score_trial_on_folds``.

Provenance notes:
- v1 winner shape 35/60/65/30 linear is read from the v1 gate record
  ``.scratch/gold_curve_search.stdout.log`` (search line + gate table), NOT
  from ``.scratch/gold_curve_search.json``, which currently holds the v2-full
  record (gvz-inclusive weights, mean OOS +3.04). The replay self-check
  (full-vote OOS reproduces the v1 gate fold-1 ``-11.19%``) proves the wiring.
- ``gold_generic_rails_fitter`` is IMPORTED from the gate script, not copied.
- Valuation z uses the frozen full-history rails (same construction as
  ``run_gold_frozen_index.py``), NOT a per-fold refit.

Usage (from the repo root of the gold worktree):
    PYTHONPATH=digiquant/src .venv/bin/python \\
        digiquant/scripts/run_gold_fold1_attribution.py

Writes ``.scratch/gold_fold1_attribution.json`` (untracked). Research-only.
"""

from __future__ import annotations

import json
import sys
from datetime import date
from pathlib import Path

import polars as pl

from digiquant.strategies.sdca.backtest import run_backtest
from digiquant.strategies.sdca.curve import AccumDistCurve
from digiquant.strategies.sdca.curve_sim import (
    DEFAULT_TRIAL_CASH,
    evaluate_sdca_trial_curve_sim,
)
from digiquant.strategies.sdca.indicator_catalog import (
    WEIGHT_PARAM_BY_NAME,
    SdcaCompositeWeights,
    extra_indicators_for_window,
    extra_z_vectors,
)
from digiquant.strategies.sdca.optimize import (
    SDCA_SHAPE_DEFAULTS,
    load_sdca_extra_sources,
)
from digiquant.strategies.sdca.providers import resolve_sdca_risk_model
from digiquant.strategies.sdca.risk_index import build_risk_index
from digiquant.strategies.sdca.walk_forward import (
    SdcaOptimizeObjective,
    WalkForwardFold,
    make_walk_forward_folds,
    score_trial_on_folds,
    shape_from_params,
    window_slice,
)

sys.path.insert(0, str(Path(__file__).resolve().parent))
from run_gold_curve_search import gold_generic_rails_fitter

DIGIQUANT_ROOT = Path(__file__).resolve().parents[1]
SEED_PATH = DIGIQUANT_ROOT / ".scratch" / "gold_seed.json"
DATA_PATH = DIGIQUANT_ROOT / "data" / "price-history" / "GLD-USD.csv"
OUT_PATH = DIGIQUANT_ROOT / ".scratch" / "gold_fold1_attribution.json"

# v1 winner (searched shape) from the v1 gate record
# .scratch/gold_curve_search.stdout.log: "winner worst_vs_flat=9.00%
# shape={'buy_max_rate': 35.0, 'buy_knee_risk': 60.0, 'sell_knee_risk': 65.0,
# 'sell_max_rate': 30.0, ...}". Single-knee (no mid-tier keys) so the gated
# projection equals the searched shape.
V1_WINNER_SHAPE: dict[str, float] = {
    "buy_max_rate": 35.0,
    "buy_knee_risk": 60.0,
    "sell_knee_risk": 65.0,
    "sell_max_rate": 30.0,
    "buy_curvature": 1.0,
    "sell_curvature": 1.0,
}
V1_GATE_FOLD1_OOS_VS_FLAT = -11.19  # v1 gate record, fold 1, feasible=True

EXPECTED_FOLD1_OOS_START = date(2013, 8, 16)
EXPECTED_FOLD1_OOS_END = date(2017, 12, 27)

SUBPERIODS: dict[str, tuple[date, date]] = {
    "crash_tail": (date(2013, 8, 16), date(2013, 12, 31)),
    "range": (date(2014, 1, 1), date(2015, 12, 31)),
    "rally": (date(2016, 1, 1), date(2016, 12, 31)),
    "breakout": (date(2017, 1, 1), date(2017, 12, 27)),
}

LEGS = ("valuation", "m2", "dxy")  # the v1 vote — the legs that actually lost
FWD_DAYS = 63


def _fold_geometry(fold: WalkForwardFold) -> dict[str, str]:
    return {
        "fold": str(fold.fold),
        "is_start": str(fold.is_start),
        "is_end": str(fold.is_end),
        "oos_start": str(fold.oos_start),
        "oos_end": str(fold.oos_end),
    }


def _sign(x: float) -> int:
    if x > 0:
        return 1
    if x < 0:
        return -1
    return 0


def _diagnose_leg(
    z_vals: list[float | None],
    fwd_vals: list[float | None],
) -> dict[str, float | int]:
    n = n_zero = 0
    hits = 0
    abs_right: list[float] = []
    abs_wrong: list[float] = []
    bias_sum = 0.0
    for z, f in zip(z_vals, fwd_vals, strict=True):
        if z is None or f is None:
            continue
        if not (z == z and f == f):  # NaN guard
            continue
        if z == 0.0 or f == 0.0:
            n_zero += 1
            continue
        n += 1
        bias_sum += z
        if _sign(z) == _sign(f):
            hits += 1
            abs_right.append(abs(z))
        else:
            abs_wrong.append(abs(z))
    if n == 0:
        raise ValueError("empty diagnostic cell — subperiod has no scored rows")
    return {
        "n": n,
        "n_zero_skipped": n_zero,
        "hit_rate": hits / n,
        "mean_abs_z_right": sum(abs_right) / len(abs_right) if abs_right else 0.0,
        "mean_abs_z_wrong": sum(abs_wrong) / len(abs_wrong) if abs_wrong else 0.0,
        "mean_z_bias": bias_sum / n,
    }


def main() -> None:
    # ---- Step 1: recompute fold dates + assert fold-1 OOS ----
    seed = json.loads(SEED_PATH.read_text())
    dates = [date.fromisoformat(d) for d in seed["dates"]]
    prices = [float(p) for p in seed["prices"]]
    weights = SdcaCompositeWeights(**seed["weights"])
    print(f"v1 seed: {dates[0]}..{dates[-1]} ({len(dates)} bars)")

    folds, holdout = make_walk_forward_folds(dates, n_folds=3, holdout_frac=0.2, oos_frac=0.25)
    fold1 = folds[1]
    if fold1.oos_start != EXPECTED_FOLD1_OOS_START or fold1.oos_end != EXPECTED_FOLD1_OOS_END:
        print("FOLD GEOMETRY MISMATCH — refusing to proceed on wrong windows", file=sys.stderr)
        print(
            f"  expected fold-1 OOS: {EXPECTED_FOLD1_OOS_START}..{EXPECTED_FOLD1_OOS_END}",
            file=sys.stderr,
        )
        print(f"  recomputed fold-1 OOS: {fold1.oos_start}..{fold1.oos_end}", file=sys.stderr)
        for fold in folds:
            print(f"  recomputed: {_fold_geometry(fold)}", file=sys.stderr)
        print(f"  holdout: {holdout[0]}..{holdout[1]}", file=sys.stderr)
        raise SystemExit(1)
    print(f"fold-1 OOS asserted: {fold1.oos_start}..{fold1.oos_end}")
    fold_dates = {
        "folds": [_fold_geometry(f) for f in folds],
        "holdout": [str(holdout[0]), str(holdout[1])],
        "fold1_oos_assert": f"{EXPECTED_FOLD1_OOS_START}..{EXPECTED_FOLD1_OOS_END}",
    }

    date_s = pl.Series("date", dates, dtype=pl.Date)
    price_s = pl.Series("price", prices, dtype=pl.Float64)

    # OOS date set + subperiod cuts (asserted non-empty).
    _, oos_prices_check = window_slice(dates, prices, fold1.oos_start, fold1.oos_end)
    print(f"fold-1 OOS bars: {len(oos_prices_check)}")
    sub_cuts: dict[str, list[int]] = {
        "full_oos": [i for i, d in enumerate(dates) if fold1.oos_start <= d <= fold1.oos_end]
    }
    for name, (start, end) in SUBPERIODS.items():
        idx = [i for i, d in enumerate(dates) if start <= d <= end]
        if not idx:
            raise SystemExit(f"subperiod {name} {start}..{end} is empty — aborting")
        sub_cuts[name] = idx
    for name, idx in sub_cuts.items():
        print(f"  {name}: {dates[idx[0]]}..{dates[idx[-1]]} ({len(idx)} bars)")

    # ---- Step 2: causal leg vectors + diagnostics ----
    sources = load_sdca_extra_sources(DATA_PATH.parent)
    extra_z = extra_z_vectors(date_s, price_s, weights, sources)
    frozen_model = resolve_sdca_risk_model(
        "generic_valuation", dates=date_s, price=price_s, form="log_quadratic"
    )
    extras = extra_indicators_for_window(dates, dates, extra_z, weights)
    valuation_z = build_risk_index(
        date_s, price_s, frozen_model, extras, valuation_weight=weights.valuation
    )["valuation_z"].to_list()
    leg_series: dict[str, list[float | None]] = {
        "valuation": valuation_z,
        "m2": list(extra_z["m2"]),
        "dxy": list(extra_z["dxy"]),
    }
    fwd63: list[float | None] = []
    for i, p in enumerate(prices):
        j = i + FWD_DAYS
        fwd63.append((prices[j] / p - 1.0) if j < len(prices) else None)

    diagnostics: dict[str, dict[str, dict[str, float | int]]] = {}
    for sub_name, idx in sub_cuts.items():
        diagnostics[sub_name] = {}
        for leg in LEGS:
            z_vals = [leg_series[leg][i] for i in idx]
            f_vals = [fwd63[i] for i in idx]
            n_null = sum(1 for z in z_vals if z is None)
            cell = _diagnose_leg(z_vals, f_vals)
            cell["n_null_z"] = n_null
            diagnostics[sub_name][leg] = cell
            print(
                f"  {sub_name:10s} {leg:9s} n={cell['n']} hit={cell['hit_rate']:.3f} "
                f"|z|_R={cell['mean_abs_z_right']:.2f} |z|_W={cell['mean_abs_z_wrong']:.2f} "
                f"bias={cell['mean_z_bias']:+.2f} nulls={n_null}"
            )

    # ---- Step 3: winner-shape replay with drop-one-leg ----
    seed_weight_params = {
        WEIGHT_PARAM_BY_NAME[name]: value for name, value in weights.model_dump().items()
    }
    winner_params = {**SDCA_SHAPE_DEFAULTS, **seed_weight_params, **V1_WINNER_SHAPE}
    objective = SdcaOptimizeObjective()  # gate defaults (run_sdca_walk_forward path)
    variants: dict[str, dict[str, float | int | str]] = {"full_vote": dict(winner_params)}
    for leg, param in (
        ("valuation", "valuation_weight"),
        ("m2", "m2_weight"),
        ("dxy", "dxy_weight"),
    ):
        dropped = dict(winner_params)
        dropped[param] = 0.0
        variants[f"drop_{leg}"] = dropped

    replay_table: dict[str, dict[str, float | bool | str]] = {}
    for label, params in variants.items():
        scores = score_trial_on_folds(
            params,
            dates,
            prices,
            [fold1],
            gold_generic_rails_fitter,
            evaluate_sdca_trial_curve_sim,
            objective,
            extra_z=extra_z,
        )
        assert len(scores) == 1
        oos = scores[0].out_of_sample
        replay_table[label] = {
            "oos_vs_flat_dca_pct": oos.vs_flat_dca_pct,
            "max_drawdown_pct": oos.max_drawdown_pct,
            "feasible": scores[0].feasible,
            "flips_positive": oos.vs_flat_dca_pct > 0.0,
        }
        print(
            f"  {label:13s} oos_vs_flat={oos.vs_flat_dca_pct:+.2f}% "
            f"dd={oos.max_drawdown_pct:.2f}% feasible={scores[0].feasible}"
        )
    full_oos = float(replay_table["full_vote"]["oos_vs_flat_dca_pct"])
    if abs(full_oos - V1_GATE_FOLD1_OOS_VS_FLAT) > 0.5:
        raise SystemExit(
            f"replay self-check FAILED: full-vote OOS {full_oos:+.2f}% vs v1 gate "
            f"{V1_GATE_FOLD1_OOS_VS_FLAT:+.2f}% — wiring diverged, aborting"
        )
    print(f"replay self-check ok: full-vote OOS {full_oos:+.2f}% reproduces v1 gate")

    # ONE run_backtest frame (full-vote replay) for dd timing / underwater.
    is_dates, is_prices = window_slice(dates, prices, fold1.is_start, fold1.is_end)
    oos_dates, oos_prices = window_slice(dates, prices, fold1.oos_start, fold1.oos_end)
    model = gold_generic_rails_fitter(is_dates, is_prices)
    full_weights = SdcaCompositeWeights(
        valuation=float(winner_params["valuation_weight"]),
        m2=float(winner_params["m2_weight"]),
        dxy=float(winner_params["dxy_weight"]),
    )
    oos_extras = extra_indicators_for_window(oos_dates, dates, extra_z, full_weights)
    oos_date_s = pl.Series("date", oos_dates, dtype=pl.Date)
    oos_price_s = pl.Series("price", oos_prices, dtype=pl.Float64)
    oos_index = build_risk_index(
        oos_date_s,
        oos_price_s,
        model,
        oos_extras,
        valuation_weight=full_weights.valuation,
    )
    shape = shape_from_params(winner_params)
    _report, frame = run_backtest(
        oos_date_s,
        oos_price_s,
        oos_index["risk"],
        AccumDistCurve(shape.to_nodes()),
        DEFAULT_TRIAL_CASH,
    )
    pv = frame["portfolio_value"].to_list()
    fdates = frame["date"].to_list()
    run_peak = float(pv[0])
    dd_series = [0.0] * len(pv)
    for i, v in enumerate(pv):
        run_peak = max(run_peak, float(v))
        dd_series[i] = (float(v) - run_peak) / run_peak
    trough_idx = min(range(len(pv)), key=lambda i: dd_series[i])
    worst_dd = dd_series[trough_idx]
    peak_idx = max(
        (i for i in range(trough_idx + 1) if pv[i] == max(pv[: trough_idx + 1])),
        default=0,
    )
    best_uw_len = 0
    best_uw_start = best_uw_end = 0
    i = 0
    while i < len(pv):
        if dd_series[i] < 0.0:
            j = i
            while j < len(pv) and dd_series[j] < 0.0:
                j += 1
            if j - i > best_uw_len:
                best_uw_len = j - i
                best_uw_start, best_uw_end = i, j - 1
            i = j
        else:
            i += 1
    uw_depth = abs(min(dd_series[best_uw_start : best_uw_end + 1])) * 100.0 if best_uw_len else 0.0
    frame_stats = {
        "max_drawdown_pct": abs(worst_dd) * 100.0,
        "dd_peak_date": str(fdates[peak_idx]),
        "dd_trough_date": str(fdates[trough_idx]),
        "longest_underwater_bars": best_uw_len,
        "underwater_start": str(fdates[best_uw_start]),
        "underwater_end": str(fdates[best_uw_end]),
        "underwater_worst_depth_pct": uw_depth,
    }
    print(
        f"  frame dd: peak {frame_stats['dd_peak_date']} trough "
        f"{frame_stats['dd_trough_date']} ({frame_stats['max_drawdown_pct']:.2f}%)"
    )
    print(
        f"  longest underwater: {best_uw_len} bars "
        f"{frame_stats['underwater_start']}..{frame_stats['underwater_end']}"
    )

    # Replay-rails check: valuation-z on fold-1 OOS under the IS-refit rails
    # actually used by the replay (vs the frozen rails of Step 2). Proves
    # whether the gate's own rails read the bear market as cheap.
    oos_val_index = build_risk_index(oos_date_s, oos_price_s, model, [], valuation_weight=1.0)
    oos_vz = [v for v in oos_val_index["valuation_z"].to_list() if v is not None]
    replay_rails_check = {
        "n": len(oos_vz),
        "mean_valuation_z": sum(oos_vz) / len(oos_vz),
        "frac_positive": sum(1 for v in oos_vz if v > 0) / len(oos_vz),
        "frac_pinned_at_plus3": sum(1 for v in oos_vz if v >= 3.0) / len(oos_vz),
    }
    print(
        f"  replay-rails valuation_z: mean={replay_rails_check['mean_valuation_z']:.2f} "
        f"frac>0={replay_rails_check['frac_positive']:.3f} "
        f"pinned@+3={replay_rails_check['frac_pinned_at_plus3']:.3f}"
    )

    # ---- Step 4: hypothesis (written after reading the cells) ----
    hypothesis = (
        "Fold-1 OOS (2013-08-16..2017-12-27, GLD 132.58 -> 100.50 trough -> "
        "122.23) loses because the gate's own fold-1 IS-refit rails extrapolate "
        "the 2004-2013 bull trend and pin valuation-z at +3.0 (max buy) for "
        "1094/1100 OOS bars (replay_rails_check frac_pinned_at_plus3=0.995, "
        "mean=+3.00), so the composite never leaves the buy zone and the 35%/day "
        "winner curve deploys the full book into the decline: max drawdown "
        "26.05% peaking 2013-08-27 and troughing 2015-12-17 at the bear bottom, "
        "underwater 1092/1100 bars to 2017-12-27, while flat DCA keeps averaging "
        "at lower prices. Neither macro leg offsets this: m2/dxy full-OOS hit "
        "rates are 0.462/0.511 (coin flips), systematically wrong in the "
        "crash tail (0.358/0.284), and drop_m2/drop_dxy move OOS by only "
        "+0.05pp/+0.01pp. Dropping valuation helps (+9.09pp to -2.10%) but does "
        "NOT flip fold-1 positive — the residual macro-only vote still trails "
        "flat DCA. The frozen-rails Step-2 diagnostics understate the mechanism "
        "(valuation hit 0.619 there only because full-history rails have seen "
        "the bear market); the failure is the IS-refit rails' non-extrapolation "
        "(#3173), not one bad voting leg."
    )

    OUT_PATH.write_text(
        json.dumps(
            {
                "fold_dates": fold_dates,
                "winner_shape": V1_WINNER_SHAPE,
                "winner_shape_source": "gold_curve_search.stdout.log (v1 gate record)",
                "subperiod_diagnostics": diagnostics,
                "replay_table": replay_table,
                "frame_stats": frame_stats,
                "replay_rails_check": replay_rails_check,
                "hypothesis": hypothesis,
            },
            indent=2,
        )
    )
    print(f"wrote {OUT_PATH}")


if __name__ == "__main__":
    main()
