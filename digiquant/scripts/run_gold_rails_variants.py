#!/usr/bin/env python3
"""Gold (GLD) rails-variant matrix on fold-1 — vote and shape fixed (v1), rails-only delta (#4804).

Runs 8 rails-fitter variants through ``score_trial_on_folds`` on the
recomputed + asserted fold-1 object with the v1 winner params + v1 seed
weights, recording OOS vs-flat + feasibility + dd plus pinned fraction
(``price <= low`` share) and saturated fraction (valuation-z at exactly
±3.0). No gate runs, no weight/shape changes — full-gate confirmation of
the selected configs is Task 3.

Provenance notes:
- v1 winner shape 35/60/65/30 linear is COPIED from
  ``run_gold_fold1_attribution.py`` (which reads it from the v1 gate record
  ``.scratch/gold_curve_search.stdout.log`` — NOT from
  ``.scratch/gold_curve_search.json``, which holds the v2-full record).
- ``gold_generic_rails_fitter`` (the ``quad_full`` control) is IMPORTED from
  the gate script ``run_gold_curve_search``: its top-level is
  imports/constants/defs only (``main()`` is ``__main__``-guarded), so the
  import is side-effect-free. The other 7 variant fitters are defined
  locally with the same body + added params (importing the control fitter
  cannot express per-variant kwargs).
- v1 seed weights come from ``.scratch/gold_seed.json`` at runtime (never
  re-derived); fold-1 OOS 2013-08-16..2017-12-27 is recomputed via
  ``make_walk_forward_folds`` on the v1 seed calendar and asserted.

Usage (from the repo root of the gold worktree):
    PYTHONPATH=digiquant/src .venv/bin/python digiquant/scripts/run_gold_rails_variants.py

Writes ``.scratch/gold_rails_variants.json`` (untracked). Research-only.
"""

from __future__ import annotations

import json
import sys
from collections.abc import Callable
from datetime import date
from pathlib import Path

import polars as pl

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
    SDCA_SHAPE_DEFAULTS,
    load_sdca_extra_sources,
)
from digiquant.strategies.sdca.risk_model import RiskModel
from digiquant.strategies.sdca.valuation import valuation_z_score
from digiquant.strategies.sdca.walk_forward import (
    SdcaOptimizeObjective,
    WalkForwardFold,
    make_walk_forward_folds,
    score_trial_on_folds,
    window_slice,
)

sys.path.insert(0, str(Path(__file__).resolve().parent))
from run_gold_curve_search import gold_generic_rails_fitter

DIGIQUANT_ROOT = Path(__file__).resolve().parents[1]
SEED_PATH = DIGIQUANT_ROOT / ".scratch" / "gold_seed.json"
DATA_PATH = DIGIQUANT_ROOT / "data" / "price-history" / "GLD-USD.csv"
OUT_PATH = DIGIQUANT_ROOT / ".scratch" / "gold_rails_variants.json"

# v1 winner (searched shape), copied from run_gold_fold1_attribution.py
# (source: .scratch/gold_curve_search.stdout.log v1 gate record).
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

RailsFitter = Callable[[list[date], list[float]], RiskModel]


def _make_variant_fitter(
    name: str,
    *,
    form: str = "log_quadratic",
    fit_lookback_days: int | None = None,
    max_annual_trend: float | None = None,
) -> RailsFitter:
    """Local variant of the gate-script fitter body + added Task-1 params."""

    def _fitter(dates: list[date], prices: list[float]) -> RiskModel:
        coeffs = fit_generic_valuation(
            pl.Series("date", dates, dtype=pl.Date),
            pl.Series("price", prices, dtype=pl.Float64),
            form=form,  # type: ignore[arg-type]
            fit_lookback_days=fit_lookback_days,
            max_annual_trend=max_annual_trend,
            notes=f"gold rails variant {name}; fold IS window only",
        )
        return GenericValuationRiskModel(coeffs)

    _fitter.__name__ = f"rails_fitter_{name}"
    return _fitter


VARIANT_SPECS: dict[str, dict[str, float | int | str | None]] = {
    "quad_full": {},  # control — imported gate fitter, not a local closure
    "linear_full": {"form": "log_linear"},
    "quad_3y": {"fit_lookback_days": 756},
    "quad_5y": {"fit_lookback_days": 1260},
    "quad_cap10": {"max_annual_trend": 0.10},
    "quad_cap15": {"max_annual_trend": 0.15},
    "quad_cap25": {"max_annual_trend": 0.25},
    "quad_5y_cap15": {"fit_lookback_days": 1260, "max_annual_trend": 0.15},
}


def _pinned_and_saturated(
    fitter: RailsFitter,
    dates: list[date],
    prices: list[float],
    fold: WalkForwardFold,
) -> tuple[float, float, int]:
    """Pinned + saturated fractions of fold OOS under the config's IS-fit rails."""
    is_dates, is_prices = window_slice(dates, prices, fold.is_start, fold.is_end)
    oos_dates, oos_prices = window_slice(dates, prices, fold.oos_start, fold.oos_end)
    model = fitter(is_dates, is_prices)
    rails = model.rails(pl.Series("date", oos_dates, dtype=pl.Date))
    low = rails["low"].to_list()
    pinned = sum(1 for p, lo in zip(oos_prices, low, strict=True) if p <= lo) / len(oos_prices)
    z = valuation_z_score(
        pl.Series("price", oos_prices, dtype=pl.Float64),
        rails["low"],
        rails["median"],
        rails["high"],
    ).to_list()
    scored = [v for v in z if v is not None]
    saturated = sum(1 for v in scored if v == 3.0 or v == -3.0) / len(scored)
    return pinned, saturated, len(oos_prices)


def main() -> None:
    # ---- Step 1: recompute fold dates + assert fold-1 OOS ----
    seed = json.loads(SEED_PATH.read_text())
    dates = [date.fromisoformat(d) for d in seed["dates"]]
    prices = [float(p) for p in seed["prices"]]
    weights = SdcaCompositeWeights(**seed["weights"])
    print(f"v1 seed: {dates[0]}..{dates[-1]} ({len(dates)} bars)")

    folds, _holdout = make_walk_forward_folds(dates, n_folds=3, holdout_frac=0.2, oos_frac=0.25)
    fold1 = folds[1]
    if fold1.oos_start != EXPECTED_FOLD1_OOS_START or fold1.oos_end != EXPECTED_FOLD1_OOS_END:
        print("FOLD GEOMETRY MISMATCH — refusing to proceed on wrong windows", file=sys.stderr)
        print(
            f"  expected fold-1 OOS: {EXPECTED_FOLD1_OOS_START}..{EXPECTED_FOLD1_OOS_END}",
            file=sys.stderr,
        )
        print(f"  recomputed fold-1 OOS: {fold1.oos_start}..{fold1.oos_end}", file=sys.stderr)
        raise SystemExit(1)
    print(f"fold-1 OOS asserted: {fold1.oos_start}..{fold1.oos_end}")

    date_s = pl.Series("date", dates, dtype=pl.Date)
    price_s = pl.Series("price", prices, dtype=pl.Float64)
    sources = load_sdca_extra_sources(DATA_PATH.parent)
    extra_z = extra_z_vectors(date_s, price_s, weights, sources)

    seed_weight_params = {
        WEIGHT_PARAM_BY_NAME[name]: value for name, value in weights.model_dump().items()
    }
    winner_params = {**SDCA_SHAPE_DEFAULTS, **seed_weight_params, **V1_WINNER_SHAPE}
    objective = SdcaOptimizeObjective()  # gate defaults (run_sdca_walk_forward path)

    fitters: dict[str, RailsFitter] = {"quad_full": gold_generic_rails_fitter}
    for name, spec in VARIANT_SPECS.items():
        if name == "quad_full":
            continue
        fitters[name] = _make_variant_fitter(
            name,
            form=str(spec.get("form") or "log_quadratic"),
            fit_lookback_days=spec.get("fit_lookback_days"),  # type: ignore[arg-type]
            max_annual_trend=spec.get("max_annual_trend"),  # type: ignore[arg-type]
        )

    configs: dict[str, dict[str, float | bool]] = {}
    for name in VARIANT_SPECS:
        scores = score_trial_on_folds(
            winner_params,
            dates,
            prices,
            [fold1],
            fitters[name],
            evaluate_sdca_trial_curve_sim,
            objective,
            extra_z=extra_z,
        )
        assert len(scores) == 1
        oos = scores[0].out_of_sample
        pinned, saturated, n_oos = _pinned_and_saturated(fitters[name], dates, prices, fold1)
        configs[name] = {
            "oos": oos.vs_flat_dca_pct,
            "feasible": scores[0].feasible,
            "dd": oos.max_drawdown_pct,
            "pinned_frac": pinned,
            "saturated_frac": saturated,
        }
        print(
            f"  {name:14s} oos_vs_flat={oos.vs_flat_dca_pct:+.2f}% "
            f"dd={oos.max_drawdown_pct:.2f}% feasible={scores[0].feasible} "
            f"pinned={pinned:.4f} saturated={saturated:.4f} n_oos={n_oos}"
        )

    # ---- Sanity gates (SystemExit, do not proceed on violation) ----
    quad_oos = float(configs["quad_full"]["oos"])
    if round(quad_oos, 2) != V1_GATE_FOLD1_OOS_VS_FLAT:
        raise SystemExit(
            f"sanity gate FAILED: quad_full OOS {quad_oos:+.2f}% != v1 gate fold-1 "
            f"{V1_GATE_FOLD1_OOS_VS_FLAT:+.2f}% — replay control diverged, aborting"
        )
    print(f"sanity gate ok: quad_full OOS {quad_oos:+.2f}% reproduces v1 gate fold-1")
    quad_pinned = float(configs["quad_full"]["pinned_frac"])
    if not (0.97 <= quad_pinned <= 1.0):
        raise SystemExit(
            f"sanity gate FAILED: quad_full pinned fraction {quad_pinned:.4f} not "
            "≈0.99 (the 1094/1100 finding) — methodology diverged, aborting"
        )
    print(f"sanity gate ok: quad_full pinned fraction {quad_pinned:.4f} ≈ 0.99")

    ranked = sorted(
        configs, key=lambda n: (-float(configs[n]["oos"]), float(configs[n]["pinned_frac"]))
    )
    top2 = ranked[:2]
    print(
        f"top2: {top2[0]} ({float(configs[top2[0]]['oos']):+.2f}%), "
        f"{top2[1]} ({float(configs[top2[1]]['oos']):+.2f}%)"
    )

    OUT_PATH.write_text(json.dumps({"configs": configs, "top2": top2}, indent=2))
    print(f"wrote {OUT_PATH}")


if __name__ == "__main__":
    main()
