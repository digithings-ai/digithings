#!/usr/bin/env python3
"""
Fetch real OHLCV data from Yahoo Finance and save as DigiQuant CSV format.

Usage:
  python -m digiquant.scripts.fetch_real_ohlcv --symbols AAPL MSFT --start 2024-01-01 --end 2024-12-31
  python -m digiquant.scripts.fetch_real_ohlcv --symbols AAPL --out digiquant/data/AAPL_real.csv

Requires: pip install yfinance
"""

from __future__ import annotations

import argparse
from pathlib import Path

import pandas as pd


def main() -> int:
    parser = argparse.ArgumentParser(description="Fetch real OHLCV from Yahoo Finance")
    parser.add_argument("--symbols", nargs="+", default=["AAPL"], help="Ticker symbols")
    parser.add_argument("--start", default="2024-01-01", help="Start date YYYY-MM-DD")
    parser.add_argument("--end", default="2024-12-31", help="End date YYYY-MM-DD")
    parser.add_argument("--out", type=Path, default=None, help="Output dir (default: digiquant/data) or single file")
    parser.add_argument("--interval", default="1d", choices=["1d", "1wk", "1h", "1m"], help="Bar interval")
    args = parser.parse_args()

    try:
        import yfinance as yf
    except ImportError:
        print("yfinance not installed. Run: pip install yfinance")
        return 1

    out = args.out or Path(__file__).resolve().parent.parent / "data"
    if out.suffix == ".csv":
        out_dir = out.parent
        single_file = out
    else:
        out_dir = Path(out)
        single_file = None
    out_dir.mkdir(parents=True, exist_ok=True)

    for symbol in args.symbols:
        df = yf.download(
            tickers=symbol,
            start=args.start,
            end=args.end,
            interval=args.interval,
            progress=False,
            auto_adjust=True,
        )
        if df.empty:
            print(f"Warning: No data for {symbol}")
            continue

        # yfinance returns Open, High, Low, Close, Volume (or MultiIndex for multi-ticker)
        if isinstance(df.columns, pd.MultiIndex):
            df.columns = [c[0] for c in df.columns]
        df = df.rename(columns={"Open": "open", "High": "high", "Low": "low", "Close": "close", "Volume": "volume"})
        df = df[["open", "high", "low", "close", "volume"]].dropna()
        df.index.name = "timestamp"
        df["symbol"] = symbol
        df = df.reset_index()
        df["timestamp"] = df["timestamp"].dt.tz_localize(None).astype(str).str.replace(" ", "T")

        path = single_file if single_file and len(args.symbols) == 1 else out_dir / f"{symbol}.csv"
        df.to_csv(path, index=False)
        print(f"Saved {len(df)} rows -> {path}")

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
