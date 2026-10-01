#!/usr/bin/env python3
"""Gold step-6 attribution (issue #4804): drop-one variants + rails-form challenger.

Rebuilds the frozen full-history generic_valuation model and extra_z exactly
as run_gold_frozen_index.py does, then scores fixed-shape variants with
run_backtest (raw full-history IS only -- NOT the walk-forward gate):

- seed: valuation=1.0, m2=0.5, dxy=0.5 (the searched index)
- drop_m2: valuation=1.0, dxy=0.5
- drop_dxy: valuation=1.0, m2=0.5
- valuation_only: valuation=1.0
- challenger_log_linear: seed weights on a log_linear-form frozen index

The winner shape is read from .scratch/gold_curve_search.json (frozen
snapshot, never reconstructed). A gated challenger run is warranted only if
the log_linear index is competitive here. Research-only; writes only
.scratch/gold_attribution.json (untracked).

Usage:
    uv run python digiquant/scripts/run_gold_attribution.py
    (from the repo root of the gold worktree, with the research venv's
    PYTHONPATH pointed at the worktree's digiquant/src)
"""

from __future__ import annotations

import json
from pathlib import Path

import polars as pl

from digiquant.strategies.sdca.backtest import run_backtest
from digiquant.strategies.sdca.curve import AccumDistCurve
from digiquant.strategies.sdca.curve_shape import SdcaCurveShape
from digiquant.strategies.sdca.generic_valuation import (
    GenericValuationRiskModel,
    fit_generic_valuation,
)
from digiquant.strategies.sdca.indicator_catalog import (
    SdcaCompositeWeights,
    extra_indicators_for_window,
)
from digiquant.strategies.sdca.optimize import load_sdca_extra_z, load_sdca_ohlcv
from digiquant.strategies.sdca.risk_index import build_risk_index

DIGIQUANT_ROOT = Path(__file__).resolve().parents[1]
DEFAULT_DATA_PATH = DIGIQUANT_ROOT / "data" / "price-history" / "GLD-USD.csv"
SEARCH_PATH = DIGIQUANT_ROOT / ".scratch" / "gold_curve_search.json"
OUT_PATH = DIGIQUANT_ROOT / ".scratch" / "gold_attribution.json"

INITIAL_CASH = 10_000.0


def score_variant(
    label: str,
    date_s: pl.Series,
    price_s: pl.Series,
    risk_model: GenericValuationRiskModel,
    weights: SdcaCompositeWeights,
    extra_z: dict,
    shape: SdcaCurveShape,
) -> dict:
    extras = extra_indicators_for_window(date_s.to_list(), date_s.to_list(), extra_z, weights)
    index = build_risk_index(
        date_s, price_s, risk_model, extras, valuation_weight=weights.valuation
    )
    report, _frame = run_backtest(
        date_s,
        price_s,
        index["risk"],
        AccumDistCurve(shape.to_nodes()),
        INITIAL_CASH,
    )
    out = {
        "vs_flat_dca_pct": report.vs_flat_dca_pct,
        "vs_lump_pct": report.vs_lump_pct,
        "dca_max_drawdown_pct": report.dca_max_drawdown_pct * 100.0,
    }
    print(
        f"  {label}: vs_flat={out['vs_flat_dca_pct']:+.2f}% "
        f"vs_lump={out['vs_lump_pct']:+.2f}% dd={out['dca_max_drawdown_pct']:.2f}%"
    )
    return out


def main() -> None:
    search = json.loads(SEARCH_PATH.read_text())
    weights = SdcaCompositeWeights(**search["weights"])
    shape = SdcaCurveShape(**search["search"]["shape"])
    print(f"winner shape: {shape}")
    print(f"seed weights: {weights.model_dump()}")

    dates, prices = load_sdca_ohlcv(symbols=["GLD-USD"], data_path=DEFAULT_DATA_PATH, data_dir=None)
    date_s = pl.Series("date", dates, dtype=pl.Date)
    price_s = pl.Series("price", prices, dtype=pl.Float64)
    extra_z = load_sdca_extra_z(dates, prices, data_path=DEFAULT_DATA_PATH, data_dir=None)

    # Frozen full-history fits (same construction as the seed script).
    quad_model = GenericValuationRiskModel(fit_generic_valuation(date_s, price_s))
    linear_model = GenericValuationRiskModel(
        fit_generic_valuation(date_s, price_s, form="log_linear")
    )

    variants: dict[str, tuple] = {
        "seed": (quad_model, weights),
        "drop_m2": (
            quad_model,
            SdcaCompositeWeights(valuation=1.0, m2=0.0, dxy=weights.dxy),
        ),
        "drop_dxy": (
            quad_model,
            SdcaCompositeWeights(valuation=1.0, m2=weights.m2, dxy=0.0),
        ),
        "valuation_only": (quad_model, SdcaCompositeWeights(valuation=1.0)),
        "challenger_log_linear": (linear_model, weights),
    }
    results = {}
    for label, (model, variant_weights) in variants.items():
        results[label] = score_variant(
            label, date_s, price_s, model, variant_weights, extra_z, shape
        )
    base = results["seed"]["vs_flat_dca_pct"]
    for label in results:
        results[label]["delta_vs_seed_pp"] = results[label]["vs_flat_dca_pct"] - base

    OUT_PATH.parent.mkdir(parents=True, exist_ok=True)
    OUT_PATH.write_text(json.dumps(results, indent=2))
    print(f"wrote {OUT_PATH}")


if __name__ == "__main__":
    main()
