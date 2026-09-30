#!/usr/bin/env python3
"""Gold price-family expansion experiment — ratio-leg candidates (#4804).

Materializes gdx_gld/gld_slv z-vectors alongside the six macro legs on the
gold calendar, then scores candidate weight sets on index stats only
(coverage, buy-zone share, mean risk) plus a full correlation matrix (macro
+ ratios). No backtest, no gate run — the gate plan decides drops later.

Sanity gate: the `seed` candidate must reproduce `.scratch/gold_seed.json`
risk byte-identically (max abs diff == 0.0); anything else means the loader
or blend changed under the published seed.

Research-only; writes `.scratch/gold_price_family_expansion.json`. Touches
nothing outside `.scratch/`.

Usage:
    PYTHONPATH=digiquant/src .venv/bin/python \\
        digiquant/scripts/run_gold_price_family_expansion.py
"""

from __future__ import annotations

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
SEED_PATH = DIGIQUANT_ROOT / ".scratch" / "gold_seed.json"
OUT_PATH = DIGIQUANT_ROOT / ".scratch" / "gold_price_family_expansion.json"

FULL = SdcaCompositeWeights(
    valuation=1.0,
    m2=0.5,
    dxy=0.5,
    gvz=0.5,
    walcl=0.5,
    hy_oas=0.25,
    ig_oas=0.25,
    breakeven_5y=0.25,
    nfci=0.25,
    gdx_gld=0.5,
    gld_slv=0.5,
)
CANDIDATES: dict[str, SdcaCompositeWeights] = {
    "seed": SdcaCompositeWeights(valuation=1.0, m2=0.5, dxy=0.5),
    "ratio_pair": SdcaCompositeWeights(valuation=1.0, m2=0.5, dxy=0.5, gdx_gld=0.5, gld_slv=0.5),
    "miners_only": SdcaCompositeWeights(valuation=1.0, m2=0.5, dxy=0.5, gdx_gld=0.5),
    "metal_stress_only": SdcaCompositeWeights(valuation=1.0, m2=0.5, dxy=0.5, gld_slv=0.5),
    "kitchen_sink": FULL,
    "drop_valuation_tilt": SdcaCompositeWeights(
        valuation=0.5,
        m2=0.5,
        dxy=0.5,
        gvz=0.5,
        walcl=0.5,
        hy_oas=0.25,
        ig_oas=0.25,
        breakeven_5y=0.25,
        nfci=0.25,
        gdx_gld=0.5,
        gld_slv=0.5,
    ),
}


def _stats(risk: list[float | None]) -> dict[str, float]:
    valid = [v for v in risk if v is not None]
    buy_zone = sum(1 for v in valid if v < 25.0)
    return {
        "coverage": len(valid),
        "buy_zone_share": buy_zone / max(len(valid), 1),
        "mean_risk": sum(valid) / max(len(valid), 1),
    }


def main() -> None:
    dates, prices = load_sdca_ohlcv(symbols=["GLD-USD"], data_path=DATA_PATH, data_dir=None)
    date_s = pl.Series("date", dates, dtype=pl.Date)
    price_s = pl.Series("price", prices, dtype=pl.Float64)
    model = resolve_sdca_risk_model(
        "generic_valuation", dates=date_s, price=price_s, form="log_quadratic"
    )
    sources = load_sdca_extra_sources(DATA_PATH.parent)
    present = [
        k
        for k in ("gvz", "walcl", "hy_oas", "ig_oas", "breakeven_5y", "nfci", "gdx", "slv")
        if getattr(sources, f"{k}_dates") is not None
    ]
    print(f"new legs present: {present}")
    _SOURCE_KEY = {"gdx_gld": "gdx", "gld_slv": "slv"}
    missing = {
        leg
        for leg in set(FULL.enabled_extras()) - {"valuation"} - {"m2", "dxy"}
        if _SOURCE_KEY.get(leg, leg) not in present
    }
    if missing:
        raise SystemExit(f"missing staged series for {sorted(missing)} — rerun Task 1")

    vectors = extra_z_vectors(date_s, price_s, FULL, sources)
    print(f"materialized: {sorted(vectors)}")

    seed_risk = json.loads(SEED_PATH.read_text())["risk"]
    report: dict[str, object] = {"candidates": {}, "correlations": {}}
    for name, weights in CANDIDATES.items():
        extras = extra_indicators_for_window(dates, dates, vectors, weights)
        index = build_risk_index(date_s, price_s, model, extras, valuation_weight=weights.valuation)
        risk = index["risk"].to_list()
        entry = _stats(risk)
        entry["legs"] = sorted(weights.enabled_extras())
        report["candidates"][name] = entry  # type: ignore[index]
        print(f"{name}: {entry}")
        if name == "seed":
            diff = max(
                abs(a - b)
                for a, b in zip(risk, seed_risk, strict=True)
                if a is not None and b is not None
            )
            report["seed_repro_max_abs_diff"] = diff
            print(f"seed repro max abs diff: {diff}")
            if diff != 0.0:
                raise SystemExit("seed no longer reproduces gold_seed.json — stop and investigate")

    names = [
        "m2",
        "dxy",
        "gvz",
        "walcl",
        "hy_oas",
        "ig_oas",
        "breakeven_5y",
        "nfci",
        "gdx_gld",
        "gld_slv",
    ]
    frame = pl.DataFrame({k: vectors[k] for k in names if k in vectors}).drop_nulls()
    corr = frame.corr()
    matrix = {
        row: {col: round(val, 3) for col, val in zip(corr.columns, corr.row(i), strict=True)}
        for i, row in enumerate(corr.columns)
    }
    report["correlations"] = matrix
    print(json.dumps(matrix, indent=2))

    OUT_PATH.parent.mkdir(parents=True, exist_ok=True)
    OUT_PATH.write_text(json.dumps(report, indent=2))
    print(f"wrote {OUT_PATH}")


if __name__ == "__main__":
    main()
