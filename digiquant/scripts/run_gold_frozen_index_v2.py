#!/usr/bin/env python3
"""Gold (GLD) v2 seed frozen index — broadened vote, deep legs only (#4804).

Byte-mirror of ``run_gold_frozen_index.py`` with three deltas:
``SEED_WEIGHTS`` (below), ``OUT_PATH`` (``gold_seed_v2.json``), and the
extra-z loader: ``load_sdca_extra_sources`` + ``extra_z_vectors`` (the
expansion-script call chain) instead of ``load_sdca_extra_z``, which
hardcodes m2/rs_eth/dxy by design (BTC-isolation invariant) and cannot
materialize the deep legs (Controller Ruling 4).

Weight rationale pointer: expansion-script candidate stats (gold gate-rerun
plan Task 3). gvz/walcl at seed-macro 0.5; breakeven_5y/nfci at 0.25
(narrower history / survey overlap); gdx_gld/gld_slv ratios at 0.5 (max
ratio-leg |r| 0.514 — independent votes). hy_oas/ig_oas are 0.0: the Task-2
depth verifier is red on the BAML pair (see the Task-2 gap JSON), so both
legs are excluded from the v2 vote.

Writes `.scratch/gold_seed_v2.json` (full variant, default) or
`.scratch/gold_seed_v2deep.json` (`--variant deep`: no gvz — the
v1-comparable primary, Ruling 5) for the step-5 v2 gate loop.
Research-only; touches nothing outside `.scratch/`.

Usage (gold worktree has no venv; research venv + src on PYTHONPATH):
    PYTHONPATH=digiquant/src <research-venv>/bin/python \\
        digiquant/scripts/run_gold_frozen_index_v2.py [--variant {full,deep}]
"""

from __future__ import annotations

import argparse
import json
from pathlib import Path

import polars as pl

from digiquant.strategies.sdca.indicator_catalog import (
    SdcaCompositeWeights,
    extra_indicators_for_window,
    extra_z_vectors,
)
from digiquant.strategies.sdca.optimize import (
    load_sdca_extra_sources,
    load_sdca_ohlcv,
)
from digiquant.strategies.sdca.providers import resolve_sdca_risk_model
from digiquant.strategies.sdca.risk_index import build_risk_index

DIGIQUANT_ROOT = Path(__file__).resolve().parents[1]
DATA_PATH = DIGIQUANT_ROOT / "data" / "price-history" / "GLD-USD.csv"

# Ruling 5 variants. full = fear-gauge variant (gvz binds at 2008-06);
# deep = v1-comparable primary (no gvz; hy/ig=0 in both — Task-2 red).
SEED_WEIGHTS_FULL = SdcaCompositeWeights(
    valuation=1.0,
    m2=0.5,
    dxy=0.5,
    gvz=0.5,
    walcl=0.5,
    breakeven_5y=0.25,
    nfci=0.25,
    gdx_gld=0.5,
    gld_slv=0.5,
)
SEED_WEIGHTS_DEEP = SdcaCompositeWeights(
    valuation=1.0,
    m2=0.5,
    dxy=0.5,
    walcl=0.5,
    breakeven_5y=0.25,
    nfci=0.25,
    gdx_gld=0.5,
    gld_slv=0.5,
)
VARIANT_PATHS = {
    "full": DIGIQUANT_ROOT / ".scratch" / "gold_seed_v2.json",
    "deep": DIGIQUANT_ROOT / ".scratch" / "gold_seed_v2deep.json",
}


def main() -> None:
    parser = argparse.ArgumentParser(description="Gold GLD v2 seed frozen index")
    parser.add_argument("--variant", choices=("full", "deep"), default="full")
    args = parser.parse_args()
    seed_weights = SEED_WEIGHTS_FULL if args.variant == "full" else SEED_WEIGHTS_DEEP
    out_path = VARIANT_PATHS[args.variant]
    print(f"variant: {args.variant}")

    dates, prices = load_sdca_ohlcv(symbols=["GLD-USD"], data_path=DATA_PATH, data_dir=None)
    print(f"GLD-USD {dates[0]}..{dates[-1]} ({len(dates)} daily bars)")
    date_s = pl.Series("date", dates, dtype=pl.Date)
    price_s = pl.Series("price", prices, dtype=pl.Float64)

    model = resolve_sdca_risk_model(
        "generic_valuation", dates=date_s, price=price_s, form="log_quadratic"
    )
    print("rails: generic_valuation log_quadratic (full-history frozen fit)")

    sources = load_sdca_extra_sources(DATA_PATH.parent)
    vectors = extra_z_vectors(date_s, price_s, seed_weights, sources)
    print(f"extra_z keys: {sorted(vectors)}")
    extras = extra_indicators_for_window(dates, dates, vectors, seed_weights)
    print(f"seed extras enabled: {[e.name for e in extras]}")

    index = build_risk_index(
        date_s, price_s, model, extras, valuation_weight=seed_weights.valuation
    )
    risk = index["risk"].to_list()
    valid = [v for v in risk if v is not None]
    buy_zone = sum(1 for v in valid if v < 25.0)
    print(
        f"risk coverage: {len(valid)}/{len(risk)} non-null days; "
        f"buy-zone (risk<25): {buy_zone} ({100.0 * buy_zone / max(len(valid), 1):.1f}%); "
        f"mean risk: {sum(valid) / max(len(valid), 1):.1f}"
    )
    print(f"seed weights: {seed_weights.model_dump()}")

    out_path.parent.mkdir(parents=True, exist_ok=True)
    out_path.write_text(
        json.dumps(
            {
                "dates": [str(d) for d in dates],
                "prices": prices,
                "risk": risk,
                "weights": seed_weights.model_dump(),
                "rails": "generic_valuation/log_quadratic frozen full-history fit",
            }
        )
    )
    print(f"wrote {out_path}")


if __name__ == "__main__":
    main()
