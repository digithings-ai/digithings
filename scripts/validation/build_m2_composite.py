"""Build the M2 global-liquidity composite for the M2 Liquidity strategy validation.

Two data paths:

  1. TradingView export (preferred, true 1:1)
     ``--tv-csv path.csv`` — a CSV exported from the M2 Liquidity indicator on
     TradingView with columns: time/date, total (and optionally total_shifted).
     This is the authoritative source: it IS the series TradingView scored, so a
     backtest on it reproduces TradingView exactly. Export via the indicator's
     "..." menu → Export chart data.

  2. Keyless FRED + yfinance fallback (directional only — NOT 1:1)
     Fetches US/EU/CN/JP/GB M2 from FRED's public fredgraph.csv (no API key) and
     FX from yfinance, normalizes units, and builds the composite per the Pine
     formula. ⚠️ The OECD MABMM301* series are stale/discontinued (China ends
     2018, EU/JP/GB end ~2023), so the recent composite is unreliable. The script
     prints each component's coverage so the staleness is explicit.

Output: a parquet with columns [date, total, total_shifted, roc_sig, roc_plot]
joined with the asset close, ready for digiquant.indicators.m2_signals.M2SignalComputer.

    python scripts/validation/build_m2_composite.py --asset-csv digiquant/data/validation/BTC-USD_1d.csv
    python scripts/validation/build_m2_composite.py --tv-csv tv_m2_total.csv --asset-csv ...
"""
from __future__ import annotations

import argparse
import sys
import urllib.request
from datetime import date
from pathlib import Path

import polars as pl

_SRC = Path(__file__).resolve().parents[2] / "digiquant" / "src"
if str(_SRC) not in sys.path:
    sys.path.insert(0, str(_SRC))

from digiquant.data.m2 import build_m2_composite  # noqa: E402

# FRED series IDs. US M2SL is in BILLIONS of USD; the OECD MABMM301* series are
# in raw national-currency units. We normalize US to raw (×1e9) so all terms
# share units before applying FX, matching the Pine `/1e12` composite.
_FRED = {
    "usm2": ("M2SL", 1e9),
    "eum2": ("MABMM301EZM189S", 1.0),
    "cnm2": ("MABMM301CNM189S", 1.0),
    "jpm2": ("MABMM301JPM189S", 1.0),
    "gbm2": ("MABMM301GBM189S", 1.0),
}

# yfinance FX tickers and whether to invert to get "USD per local unit".
# Pine multiplies local M2 by (USD per local), e.g. CNM2 * CNYUSD.
_FX = {
    "cnyusd": ("CNY=X", True),  # CNY=X is USD→CNY (CNY per USD); invert
    "eurusd": ("EURUSD=X", False),  # already USD per EUR
    "jpyusd": ("JPY=X", True),  # JPY=X is JPY per USD; invert
    "gbpusd": ("GBPUSD=X", False),  # already USD per GBP
}


def _fetch_fred(series_id: str, scale: float) -> pl.DataFrame:
    url = f"https://fred.stlouisfed.org/graph/fredgraph.csv?id={series_id}"
    with urllib.request.urlopen(url, timeout=30) as r:
        text = r.read().decode()
    dates: list[date] = []
    vals: list[float] = []
    for line in text.strip().splitlines()[1:]:
        d, v = line.split(",")
        if v in (".", ""):
            continue
        dates.append(date.fromisoformat(d))
        vals.append(float(v) * scale)
    return pl.DataFrame({"date": dates, "value": vals})


def _fetch_fx(ticker: str, invert: bool) -> pl.DataFrame:
    import yfinance as yf

    hist = yf.Ticker(ticker).history(period="max", auto_adjust=True)[["Close"]]
    hist.index = [d.date() for d in hist.index]
    df = pl.DataFrame(
        {"date": list(hist.index), "value": [float(x) for x in hist["Close"].tolist()]}
    )
    if invert:
        df = df.with_columns((1.0 / pl.col("value")).alias("value"))
    return df


def _load_asset_close(path: str | Path) -> pl.DataFrame:
    df = pl.read_csv(path)
    return df.select(
        pl.col("timestamp").str.to_date().alias("date"),
        pl.col("close").cast(pl.Float64),
    )


def _coverage(label: str, df: pl.DataFrame) -> str:
    if df.is_empty():
        return f"  {label:8s}: EMPTY"
    lo, hi = df["date"].min(), df["date"].max()
    stale = "  ⚠️ STALE" if hi < date(2025, 1, 1) else ""
    return f"  {label:8s}: {lo} → {hi}  ({df.height} obs){stale}"


def build_from_fred(offset_days: int, roc_length: int) -> tuple[pl.DataFrame, list[str]]:
    notes: list[str] = ["Source: FRED (keyless) + yfinance FX — DIRECTIONAL ONLY, not 1:1."]
    fred = {}
    for key, (sid, scale) in _FRED.items():
        df = _fetch_fred(sid, scale)
        fred[key] = df
        notes.append(_coverage(key, df))
    fx = {}
    for key, (ticker, invert) in _FX.items():
        df = _fetch_fx(ticker, invert)
        fx[key] = df
        notes.append(_coverage(key, df))
    composite = build_m2_composite(
        usm2=fred["usm2"], cnm2=fred["cnm2"], cnyusd=fx["cnyusd"],
        eum2=fred["eum2"], eurusd=fx["eurusd"], jpm2=fred["jpm2"], jpyusd=fx["jpyusd"],
        gbm2=fred["gbm2"], gbpusd=fx["gbpusd"], offset_days=offset_days, roc_length=roc_length,
    )
    return composite, notes


def build_from_tv(tv_csv: str | Path, offset_days: int, roc_length: int) -> tuple[pl.DataFrame, list[str]]:
    """Build composite from a TradingView export of the `total` series."""
    raw = pl.read_csv(tv_csv)
    # Accept common TradingView column names.
    cols = {c.lower(): c for c in raw.columns}
    date_col = next((cols[c] for c in ("time", "date", "datetime") if c in cols), raw.columns[0])
    total_col = next((cols[c] for c in ("total", "plot", "m2", "value") if c in cols), None)
    if total_col is None:
        raise ValueError(
            f"Could not find a 'total' column in {tv_csv}. Columns: {raw.columns}. "
            "Export the M2 indicator's `total` plot."
        )
    df = raw.select(
        pl.col(date_col).cast(pl.Utf8).str.slice(0, 10).str.to_date().alias("date"),
        pl.col(total_col).cast(pl.Float64).alias("total"),
    ).sort("date")
    df = df.with_columns(pl.col("total").shift(offset_days).alias("total_shifted"))
    df = df.with_columns([
        (100.0 * (pl.col("total_shifted") - pl.col("total_shifted").shift(roc_length))
         / pl.col("total_shifted").shift(roc_length)).alias("roc_sig"),
        (100.0 * (pl.col("total") - pl.col("total").shift(roc_length))
         / pl.col("total").shift(roc_length)).alias("roc_plot"),
    ])
    return df, [f"Source: TradingView export {tv_csv} — authoritative (1:1)."]


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--tv-csv", help="TradingView export of the M2 `total` series (preferred).")
    ap.add_argument("--asset-csv", required=True, help="Daily OHLCV CSV of the traded asset (BTC).")
    ap.add_argument("--offset-days", type=int, default=86)
    ap.add_argument("--roc-length", type=int, default=100)
    ap.add_argument("--out", default="digiquant/data/validation/m2_composite.parquet")
    args = ap.parse_args()

    if args.tv_csv:
        composite, notes = build_from_tv(args.tv_csv, args.offset_days, args.roc_length)
    else:
        composite, notes = build_from_fred(args.offset_days, args.roc_length)

    asset = _load_asset_close(args.asset_csv)
    merged = composite.join(asset, on="date", how="inner")

    out = Path(args.out)
    out.parent.mkdir(parents=True, exist_ok=True)
    merged.write_parquet(out)

    print("M2 composite build")
    print("=" * 60)
    for n in notes:
        print(n)
    print("-" * 60)
    print(f"  composite rows : {composite.height}")
    print(f"  merged w/asset : {merged.height}  ({merged['date'].min()} → {merged['date'].max()})")
    nonnull = merged.filter(pl.col("roc_sig").is_not_null()).height
    print(f"  rows w/ signal : {nonnull}")
    print(f"  written        : {out}")


if __name__ == "__main__":
    main()
