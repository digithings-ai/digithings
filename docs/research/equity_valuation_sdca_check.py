#!/usr/bin/env python3
"""Throwaway historical check for docs/research/equity-valuation-for-sdca.md (#3176).

Fetches public FRED *graph* CSVs (current vintage, no API key) and prints Buffett-indicator
levels at known US equity tops/bottoms. Not a production ingest — production stays
``digiquant.data.prices.macro_ingest.fetch_fred`` + ``FRED_API_KEY``.

CAPE prints in the markdown were read once from Shiller's public ``ie_data.xls`` and are
not recomputed here (that workbook is xls; this script stays Polars/stdlib-only).

Usage (from repo root, network required)::

    PATH="$PWD/.venv/bin:$PATH" python docs/research/equity_valuation_sdca_check.py
"""

from __future__ import annotations

import io
import sys
import urllib.request
from datetime import date

import polars as pl

FRED_GRAPH = "https://fred.stlouisfed.org/graph/fredgraph.csv?id={id}&cosd={start}"
EVENT_QUARTERS = (
    date(2000, 1, 1),
    date(2000, 4, 1),
    date(2009, 1, 1),
    date(2009, 4, 1),
    date(2020, 1, 1),
    date(2020, 4, 1),
    date(2021, 7, 1),
    date(2021, 10, 1),
)


def _fred_csv(series_id: str, start: str) -> pl.DataFrame:
    url = FRED_GRAPH.format(id=series_id, start=start)
    with urllib.request.urlopen(url, timeout=30) as resp:
        body = resp.read()
    frame = pl.read_csv(io.BytesIO(body))
    value_col = [c for c in frame.columns if c != "observation_date"][0]
    return (
        frame.rename({"observation_date": "obs_date", value_col: "value"})
        .with_columns(
            pl.col("obs_date").str.to_date(),
            pl.col("value").cast(pl.Float64, strict=False),
        )
        .drop_nulls("value")
        .select("obs_date", "value")
    )


def _pct_rank(value: float, series: pl.Series) -> float:
    n = int((series <= value).sum())
    return 100.0 * n / series.len()


def main() -> int:
    gdp = _fred_csv("GDP", "1947-01-01").rename({"value": "gdp_billions"})
    eq = _fred_csv("NCBEILQ027S", "1945-01-01").rename({"value": "equity_millions"})
    joined = eq.join(gdp, on="obs_date", how="inner").with_columns(
        (pl.col("equity_millions") / 1000.0 / pl.col("gdp_billions") * 100.0).alias("buffett_pct")
    )
    ratios = joined.get_column("buffett_pct")
    print(
        f"Buffett points={joined.height} "
        f"first={joined['obs_date'][0]} last={joined['obs_date'][-1]}"
    )
    print(f"{'obs_date':<12} {'buffett_pct':>12} {'pctile':>8}")
    for q in EVENT_QUARTERS:
        row = joined.filter(pl.col("obs_date") == q)
        if row.is_empty():
            print(f"{q.isoformat():<12} {'(missing)':>12}")
            continue
        val = float(row["buffett_pct"][0])
        print(f"{q.isoformat():<12} {val:12.1f} {_pct_rank(val, ratios):8.1f}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
