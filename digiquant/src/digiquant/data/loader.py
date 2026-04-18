"""Polars-only OHLCV load and synthetic data. No pandas."""

from __future__ import annotations

from datetime import datetime
from pathlib import Path

import polars as pl

# Standard column names for OHLCV (asset-agnostic contract).
OHLCV_COLUMNS = ("timestamp", "open", "high", "low", "close", "volume", "symbol")


def load_ohlcv_csv(path: str | Path) -> pl.DataFrame:
    """
    Load a single OHLCV CSV with Polars.
    Expected columns: timestamp (or datetime), open, high, low, close, volume; optional symbol.
    """
    path = Path(path)
    if not path.exists():
        raise FileNotFoundError(str(path))
    df = pl.read_csv(path, try_parse_dates=True)
    # Normalize: ensure timestamp column (rename datetime/date if present)
    for col in ("datetime", "date", "time"):
        if col in df.columns and "timestamp" not in df.columns:
            df = df.rename({col: "timestamp"})
    required = {"open", "high", "low", "close", "volume"}
    missing = required - set(df.columns)
    if missing:
        raise ValueError(f"CSV missing columns: {missing}. Got: {list(df.columns)}")
    if "symbol" not in df.columns and "timestamp" in df.columns:
        df = df.with_columns(pl.lit(path.stem.split("_")[0]).alias("symbol"))
    return df


def generate_synthetic_ohlcv(
    symbols: list[str],
    start_date: str = "2024-01-01",
    end_date: str = "2024-12-31",
    freq: str = "1d",
    seed: int = 42,
) -> pl.DataFrame:
    """
    Generate synthetic OHLCV with Polars (for tests and demos).
    Returns one row per (timestamp, symbol) with deterministic prices.
    """
    def _parse(s: str) -> datetime:
        if "T" in s:
            return datetime.fromisoformat(s.replace("Z", "+00:00"))
        return datetime.fromisoformat(s + "T00:00:00")

    start_dt = _parse(start_date)
    end_dt = _parse(end_date)
    ts = pl.datetime_range(start=start_dt, end=end_dt, interval=freq, eager=True)
    n = len(ts)
    out: list[pl.DataFrame] = []
    for i, sym in enumerate(symbols):
        rng = seed + i * 1000
        base = 100.0 + (rng % 50)
        open_ = [base + (j % 10) - 5.0 for j in range(n)]
        high = [open_[j] + 1.0 + (rng + j) % 3 for j in range(n)]
        low = [open_[j] - 1.0 - (rng + j + 1) % 3 for j in range(n)]
        close = [
            low[j] + (high[j] - low[j]) * 0.5 + 0.1 * ((j + rng) % 5 - 2)
            for j in range(n)
        ]
        vol = [1000.0 + (rng + j) % 5000 for j in range(n)]
        df = pl.DataFrame({
            "timestamp": ts,
            "open": open_,
            "high": high,
            "low": low,
            "close": close,
            "volume": vol,
            "symbol": sym,
        })
        out.append(df)
    return pl.concat(out).sort(["symbol", "timestamp"])


def list_symbols_from_dir(data_dir: str | Path) -> list[str]:
    """List symbols from CSV filenames in data_dir (e.g. AAPL.csv -> AAPL)."""
    data_dir = Path(data_dir)
    if not data_dir.is_dir():
        return []
    symbols: list[str] = []
    for f in data_dir.iterdir():
        if f.suffix.lower() == ".csv":
            symbols.append(f.stem.split("_")[0].split("-")[0])
    return sorted(set(symbols))
