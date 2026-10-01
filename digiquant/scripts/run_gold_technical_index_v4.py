#!/usr/bin/env python3
"""Gold (GLD) v4 seed technical index — rolling anchor, no time trend (#4804).

Byte-mirror of ``run_gold_frozen_index_v2.py`` (imports/flow/output shape)
with a new vote: trailing ``rolling_z`` rails instead of a frozen
full-history time-trend fit, plus macro/dollar (m2/uup) and the
three price oscillators (weekly_rsi/weekly_macd/sma_band).

Rails: ``resolve_sdca_risk_model("rolling_z", ...)`` with window 90 / z 1.0
as literal constants (90d matches the oscillator horizon family; sensitivity
to these is a follow-up, not this task). No time-trend import or fit
anywhere in this file — the rolling path needs none of it.

Weight rationale: valuation 1.0 (rolling anchor is the vote's center), m2/uup
at seed-macro 0.5 (parity with the v3 uupswap macro leg), oscillators at
quarter-weight 0.25 starters — the Task-4 gate decides whether they earn
their keep; small enough to observe, large enough to matter in the blend.

Overlap disclosure: ``sma_band`` (price vs trailing SMA, mean-reversion) and
the ``rolling_z`` rails anchor (price vs 90d trailing mean, mean-reversion)
are overlapping signals — both go long cheap-vs-trailing-mean. The anchor
carries full weight 1.0 while sma_band carries 0.25, so the double-count is
bounded but real; the gate compares v4 against v3 (no oscillators) to price
it.

Writes `.scratch/gold_seed_v4.json` for the Task-4 gate loop.

Usage (gold worktree has no venv; research venv + src on PYTHONPATH):
    PYTHONPATH=digiquant/src <research-venv>/bin/python \\
        digiquant/scripts/run_gold_technical_index_v4.py
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
OUT_PATH = DIGIQUANT_ROOT / ".scratch" / "gold_seed_v4.json"

SEED_WEIGHTS = SdcaCompositeWeights(
    valuation=1.0,
    m2=0.5,
    uup=0.5,
    weekly_rsi=0.25,
    weekly_macd=0.25,
    sma_band=0.25,
)


def main() -> None:
    dates, prices = load_sdca_ohlcv(symbols=["GLD-USD"], data_path=DATA_PATH, data_dir=None)
    print(f"GLD-USD {dates[0]}..{dates[-1]} ({len(dates)} daily bars)")
    date_s = pl.Series("date", dates, dtype=pl.Date)
    price_s = pl.Series("price", prices, dtype=pl.Float64)

    # 90d matches the oscillator horizon family; sensitivity is a follow-up.
    model = resolve_sdca_risk_model(
        "rolling_z", dates=date_s, price=price_s, rolling_window=90, rolling_z=1.0
    )
    print("rails: rolling_z 90d/z1.0 trailing mean-reversion (no time trend)")

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
    buy_zone = sum(1 for v in valid if v < 25.0)
    print(
        f"risk coverage: {len(valid)}/{len(risk)} non-null days; "
        f"buy-zone (risk<25): {buy_zone} ({100.0 * buy_zone / max(len(valid), 1):.1f}%); "
        f"mean risk: {sum(valid) / max(len(valid), 1):.1f}"
    )
    print(f"seed weights: {SEED_WEIGHTS.model_dump()}")

    OUT_PATH.parent.mkdir(parents=True, exist_ok=True)
    OUT_PATH.write_text(
        json.dumps(
            {
                "dates": [str(d) for d in dates],
                "prices": prices,
                "risk": risk,
                "weights": SEED_WEIGHTS.model_dump(),
                "rails": "rolling_z/90d/z1.0 trailing mean-reversion (no time trend)",
                "trend_valuation": False,
            }
        )
    )
    print(f"wrote {OUT_PATH}")


if __name__ == "__main__":
    main()
