#!/usr/bin/env python3
"""Gold (GLD) seed frozen index — METHOD.md checklist steps 3+4 (#4804).

Builds the first gold valuation index on develop naming (`valuation` leg,
not the research-branch `power_law` rename):

- rails: generic_valuation log_quadratic fit on the FULL GLD history
  (frozen-index caveat, same as the BTC Task-7 frozen index — the
  walk-forward gate refits per fold instead);
- extras: M2 + DXY from the sibling CSVs (both present, local-only);
  rs_eth omitted (no ETH sibling for gold — and BTC/ETH RS is meaningless
  for a gold book); oscillators computed from GLD close, weight 0 at seed;
- seed weights: valuation=1.0, m2=0.5, dxy=0.5 (BTC live-weight macro
  convention as the starting point; the loop moves them from here).

Writes `.scratch/gold_seed.json` (dates/prices/risk/weights) for the
step-5 loop. Research-only; touches nothing outside `.scratch/`.

Usage (gold worktree has no venv; research venv + src on PYTHONPATH):
    PYTHONPATH=digiquant/src <research-venv>/bin/python \\
        digiquant/scripts/run_gold_frozen_index.py
"""

from __future__ import annotations

import json
from pathlib import Path

import polars as pl

from digiquant.strategies.sdca.indicator_catalog import (
    SdcaCompositeWeights,
    extra_indicators_for_window,
)
from digiquant.strategies.sdca.optimize import load_sdca_extra_z, load_sdca_ohlcv
from digiquant.strategies.sdca.providers import resolve_sdca_risk_model
from digiquant.strategies.sdca.risk_index import build_risk_index

DIGIQUANT_ROOT = Path(__file__).resolve().parents[1]
DATA_PATH = DIGIQUANT_ROOT / "data" / "price-history" / "GLD-USD.csv"
OUT_PATH = DIGIQUANT_ROOT / ".scratch" / "gold_seed.json"

SEED_WEIGHTS = SdcaCompositeWeights(valuation=1.0, m2=0.5, dxy=0.5)


def main() -> None:
    dates, prices = load_sdca_ohlcv(symbols=["GLD-USD"], data_path=DATA_PATH, data_dir=None)
    print(f"GLD-USD {dates[0]}..{dates[-1]} ({len(dates)} daily bars)")
    date_s = pl.Series("date", dates, dtype=pl.Date)
    price_s = pl.Series("price", prices, dtype=pl.Float64)

    model = resolve_sdca_risk_model(
        "generic_valuation", dates=date_s, price=price_s, form="log_quadratic"
    )
    print("rails: generic_valuation log_quadratic (full-history frozen fit)")

    extra_z = load_sdca_extra_z(dates, prices, data_path=DATA_PATH, data_dir=None)
    print(f"extra_z keys: {sorted(extra_z)}")
    extras = extra_indicators_for_window(dates, dates, extra_z, SEED_WEIGHTS)
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
                "rails": "generic_valuation/log_quadratic frozen full-history fit",
            }
        )
    )
    print(f"wrote {OUT_PATH}")


if __name__ == "__main__":
    main()
