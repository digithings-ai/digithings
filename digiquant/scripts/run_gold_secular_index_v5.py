#!/usr/bin/env python3
"""Gold (GLD) v5 seed secular index — long trailing anchor, no time trend (#4804).

Byte-mirror of ``run_gold_technical_index_v4.py`` (imports/flow/output shape)
with a new vote: a secular-scale trailing ``rolling_z`` anchor plus slow macro
(m2/uup) only — no oscillators, no time trend.

Rails: ``resolve_sdca_risk_model("rolling_z", ...)`` with window 1260 / z 1.0
as literal constants (frozen by Plan 13, not tuned). No time-trend import or
fit anywhere in this file — the rolling path needs none of it.

Weight rationale: valuation 1.0 (the secular anchor is the vote's center),
m2/uup at seed-macro 0.5 (parity with the v3/v4 macro leg — slow
liquidity/dollar drifts that do not fight the secular grind). ALL oscillators
(weekly_rsi/weekly_macd/sma_band) are 0.0: short-horizon votes sell the grind,
and selling grinding rallies is exactly the drag that keeps a secular-bull
vote below lump — zeroing them is the lump-beating requirement, not an
oversight. The v4 sma_band overlap question (sma_band vs rolling anchor
double-counting cheap-vs-trailing-mean) is MOOT here since sma_band=0.

Writes `.scratch/gold_seed_v5.json` for the Plan 13 gate loop.

Usage (gold worktree has no venv; research venv + src on PYTHONPATH):
    PYTHONPATH=digiquant/src <research-venv>/bin/python \\
        digiquant/scripts/run_gold_secular_index_v5.py
"""

from __future__ import annotations

import json
import sys
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
OUT_PATH = DIGIQUANT_ROOT / ".scratch" / "gold_seed_v5.json"

SEED_WEIGHTS = SdcaCompositeWeights(
    valuation=1.0,
    m2=0.5,
    uup=0.5,
)


def main() -> None:
    dates, prices = load_sdca_ohlcv(symbols=["GLD-USD"], data_path=DATA_PATH, data_dir=None)
    print(f"GLD-USD {dates[0]}..{dates[-1]} ({len(dates)} daily bars)")
    date_s = pl.Series("date", dates, dtype=pl.Date)
    price_s = pl.Series("price", prices, dtype=pl.Float64)

    # 1260d ≈ 5yr ≈ half of gold's ~decadal secular swing per the Plan 13
    # header (2001-11 bull / 2011-15 bear / 2015-26 bull); frozen vote, not tuned.
    model = resolve_sdca_risk_model(
        "rolling_z", dates=date_s, price=price_s, rolling_window=1260, rolling_z=1.0
    )
    print("rails: rolling_z 1260d/z1.0 secular trailing mean (no time trend)")

    sources = load_sdca_extra_sources(DATA_PATH.parent)
    vectors = extra_z_vectors(date_s, price_s, SEED_WEIGHTS, sources)
    print(f"extra_z keys: {sorted(vectors)}")
    extras = extra_indicators_for_window(dates, dates, vectors, SEED_WEIGHTS)
    print(f"seed extras enabled: {[e.name for e in extras]}")

    index = build_risk_index(
        date_s, price_s, model, extras, valuation_weight=SEED_WEIGHTS.valuation
    )
    risk = index["risk"].to_list()
    valid = [v for v in risk if v is not None]
    coverage = len(valid) / max(len(risk), 1)
    if coverage < 0.80:
        print(
            f"STOP: risk coverage {len(valid)}/{len(risk)} ({100.0 * coverage:.1f}%) "
            "below the 80% tripwire — finding, not a tuning prompt; window stays 1260.",
            file=sys.stderr,
        )
        raise SystemExit(1)
    buy_zone = sum(1 for v in valid if v < 25.0)
    print(
        f"risk coverage: {len(valid)}/{len(risk)} non-null days; "
        f"buy-zone (risk<25): {buy_zone} ({100.0 * buy_zone / max(len(valid), 1):.1f}%); "
        f"mean risk: {sum(valid) / max(len(valid), 1):.1f}"
    )
    # Null-footprint tripwire: a null-risk day counts as valuation-attributable
    # only if the valuation leg is null while every enabled extra is present
    # (a day null on all legs would be null regardless — not an omission fix
    # regression). STOP if nonzero.
    val_z = index["valuation_z"].to_list()
    extra_z_lists = [index[f"{e.name}_z"].to_list() for e in extras]
    val_attrib = sum(
        1
        for i, v in enumerate(risk)
        if v is None and val_z[i] is None and all(col[i] is not None for col in extra_z_lists)
    )
    print(f"valuation-attributable nulls: {val_attrib} (tripwire: must be 0)")
    if val_attrib != 0:
        print(
            f"STOP: {val_attrib} null-risk days attributable to valuation — "
            "omission-fix regression; do not mask.",
            file=sys.stderr,
        )
        raise SystemExit(1)
    print(f"seed weights: {SEED_WEIGHTS.model_dump()}")

    OUT_PATH.parent.mkdir(parents=True, exist_ok=True)
    OUT_PATH.write_text(
        json.dumps(
            {
                "dates": [str(d) for d in dates],
                "prices": prices,
                "risk": risk,
                "weights": SEED_WEIGHTS.model_dump(),
                "rails": "rolling_z/1260d/z1.0 secular trailing mean (no time trend)",
                "trend_valuation": False,
            }
        )
    )
    print(f"wrote {OUT_PATH}")


if __name__ == "__main__":
    main()
