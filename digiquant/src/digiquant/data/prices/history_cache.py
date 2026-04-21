"""Local OHLCV CSV cache — Polars-only.

Ported from ``apps/digiquant-atlas/scripts/preload-history.py``.

One CSV per ticker at ``<cache_dir>/<TICKER>.csv`` with columns
``timestamp, open, high, low, close, volume, symbol`` (matches
:data:`digiquant.data.prices.OHLCV_COLUMNS`).

The cache is intentionally flat CSV (no parquet) because Atlas' legacy
pipeline also reads these files, and we want cross-compatibility during the
grace period. Writes are atomic (temp file + rename).
"""

from __future__ import annotations

from datetime import date, timedelta
from pathlib import Path

import polars as pl

from digiquant.data.prices import OHLCV_COLUMNS
from digiquant.data.prices.fetchers import FetchResult, fetch_batch

DEFAULT_CACHE_DIR = Path("data/price-history")


def cache_path(ticker: str, cache_dir: Path | str = DEFAULT_CACHE_DIR) -> Path:
    return Path(cache_dir) / f"{ticker}.csv"


def load_cached(ticker: str, cache_dir: Path | str = DEFAULT_CACHE_DIR) -> pl.DataFrame | None:
    """Load a cached ticker CSV. Returns ``None`` if missing or empty."""
    p = cache_path(ticker, cache_dir)
    if not p.exists():
        return None
    try:
        df = pl.read_csv(p, try_parse_dates=True)
    except Exception:
        return None
    if df.is_empty():
        return None
    # Normalize column names (legacy atlas caches use capitalized columns).
    lower = {c: c.lower() for c in df.columns if c != c.lower()}
    if lower:
        df = df.rename(lower)
    if "timestamp" not in df.columns:
        for alt in ("date", "datetime"):
            if alt in df.columns:
                df = df.rename({alt: "timestamp"})
                break
    if "symbol" not in df.columns:
        df = df.with_columns(pl.lit(ticker).alias("symbol"))
    return df.sort("timestamp")


def save_cached(ticker: str, df: pl.DataFrame, cache_dir: Path | str = DEFAULT_CACHE_DIR) -> Path:
    """Atomically persist a ticker's OHLCV frame to CSV.

    The on-disk file uses the canonical ``OHLCV_COLUMNS`` layout. Extra columns
    are dropped; missing columns raise ``ValueError``.
    """
    missing = set(OHLCV_COLUMNS) - set(df.columns)
    if missing:
        raise ValueError(f"save_cached({ticker}): missing columns {missing}")
    cdir = Path(cache_dir)
    cdir.mkdir(parents=True, exist_ok=True)
    dest = cache_path(ticker, cdir)
    tmp = dest.with_suffix(".csv.tmp")
    df.select(list(OHLCV_COLUMNS)).sort("timestamp").write_csv(tmp)
    tmp.rename(dest)
    return dest


def incremental_update(
    tickers: list[str],
    cache_dir: Path | str = DEFAULT_CACHE_DIR,
    *,
    bulk_period: str = "3mo",
    dry_run: bool = False,
) -> dict[str, pl.DataFrame]:
    """Incrementally update cached tickers; bulk-fetch uncached ones.

    For each ticker:

    * If no cache → add to a "bulk" batch that fetches ``bulk_period`` history.
    * If cache exists and ``last_date < today`` → fetch ``last_date + 1 … today``.
    * Cache already current → reuse in-memory.

    Returns ``{ticker: merged_polars_df}``.
    """
    uncached: list[str] = []
    to_update: list[tuple[str, pl.DataFrame, str]] = []  # (ticker, existing_df, fetch_start)

    today = date.today()
    today_s = today.isoformat()
    for t in tickers:
        cached = load_cached(t, cache_dir)
        if cached is None:
            uncached.append(t)
        else:
            last_ts = cached.select(pl.col("timestamp").max()).item()
            last_d = (
                last_ts.date()
                if hasattr(last_ts, "date")
                else date.fromisoformat(str(last_ts)[:10])
            )
            start = (last_d + timedelta(days=1)).isoformat()
            if start <= today_s:
                to_update.append((t, cached, start))
            else:
                to_update.append((t, cached, ""))  # already current

    result: dict[str, pl.DataFrame] = {}

    if uncached:
        bulk: FetchResult = fetch_batch(uncached, period=bulk_period, dry_run=dry_run)
        for t, df in bulk.frames.items():
            save_cached(t, df, cache_dir)
            result[t] = df

    if to_update:
        stale = [(t, df, s) for t, df, s in to_update if s]
        if stale:
            earliest = min(s for _, _, s in stale)
            fetch_tickers = [t for t, _, _ in stale]
            new_result: FetchResult = fetch_batch(
                fetch_tickers,
                start=earliest,
                end=today_s,
                dry_run=dry_run,
            )
            for t, old, _ in stale:
                new = new_result.frames.get(t)
                merged = _merge_ohlcv(old, new) if new is not None else old
                save_cached(t, merged, cache_dir)
                result[t] = merged
        for t, old, s in to_update:
            if t not in result:
                result[t] = old

    return result


def preload_history(
    tickers: list[str],
    cache_dir: Path | str = DEFAULT_CACHE_DIR,
    *,
    period: str = "2y",
    dry_run: bool = False,
) -> dict[str, pl.DataFrame]:
    """One-shot bulk download, overwriting the cache for each ticker."""
    result = fetch_batch(tickers, period=period, dry_run=dry_run)
    for t, df in result.frames.items():
        save_cached(t, df, cache_dir)
    return result.frames


def _merge_ohlcv(old: pl.DataFrame, new: pl.DataFrame) -> pl.DataFrame:
    """Combine two OHLCV frames, taking the later row on duplicate timestamps."""
    if new is None or new.is_empty():
        return old
    if old is None or old.is_empty():
        return new
    # unique(subset='timestamp', keep='last') after concat, keeping legacy rows overridden by new fetch.
    return (
        pl.concat([old, new], how="vertical_relaxed")
        .unique(subset=["timestamp"], keep="last", maintain_order=False)
        .sort("timestamp")
    )


__all__ = [
    "DEFAULT_CACHE_DIR",
    "cache_path",
    "incremental_update",
    "load_cached",
    "preload_history",
    "save_cached",
]
