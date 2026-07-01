#!/usr/bin/env python3
"""
Price history cache pre-loader.

Downloads historical OHLCV data from Yahoo Finance, writes to a local Parquet
cache (data/price-history/), and optionally upserts to a Supabase
``price_history`` table.

Usage:
    python scripts/preload-history.py
    python scripts/preload-history.py --refresh
    python scripts/preload-history.py --refresh --max-stale-days 1 --supabase

Requires:
    pip install yfinance polars
    pip install supabase   # only when --supabase is used
"""

from __future__ import annotations

import argparse
import math
import os
import re
import sys
from datetime import datetime, timezone
from pathlib import Path

import polars as pl

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "digiquant" / "src"))
from digiquant.data.prices._utils import call_with_retry  # noqa: E402

# ---------------------------------------------------------------------------
# Constants
# ---------------------------------------------------------------------------

REPO_ROOT = Path(__file__).resolve().parent.parent
DEFAULT_CACHE_DIR = REPO_ROOT / "data" / "price-history"
WATCHLIST_PATH = REPO_ROOT / "config" / "watchlist.md"
BATCH_SIZE = 25
DEFAULT_PERIOD = "2y"

# yfinance column names → normalised names used throughout this script
_COL_MAP: dict[str, str] = {
    "Date": "date",
    "Datetime": "date",
    "Open": "open",
    "High": "high",
    "Low": "low",
    "Close": "close",
    "Adj Close": "adj_close",
    "Volume": "volume",
}

# ---------------------------------------------------------------------------
# Watchlist parsing
# ---------------------------------------------------------------------------

# Matches 1-5 uppercase letters, optionally followed by a dot and 1-2 more.
_TICKER_RE = re.compile(r"\b([A-Z]{1,5}(?:\.[A-Z]{1,2})?)\b")
_STOPWORDS = frozenset(
    {
        "A", "AN", "AND", "ARE", "AS", "AT", "BE", "BY", "DO", "FOR",
        "FROM", "IF", "IN", "IS", "IT", "NA", "NO", "NOT", "OF", "ON",
        "OR", "THE", "TO", "US", "UK", "ETF", "TBD", "OHLCV", "CSV",
        "API", "URL", "UTC", "EOF", "SEC", "NYSE", "NASDAQ",
    }
)


def parse_watchlist(path: Path) -> list[str]:
    """Extract deduplicated ticker symbols from a Markdown watchlist file.

    Looks for bare uppercase tokens on non-heading lines (table cells, list
    items, inline code spans, etc.).  Common English abbreviations are filtered
    out via a stopword list.
    """
    seen: set[str] = set()
    tickers: list[str] = []

    for line in path.read_text(encoding="utf-8").splitlines():
        stripped = line.strip()
        if not stripped or stripped.startswith("#"):
            continue
        for m in _TICKER_RE.finditer(stripped):
            tok = m.group(1)
            if tok in _STOPWORDS:
                continue
            if tok not in seen:
                seen.add(tok)
                tickers.append(tok)

    return tickers


# ---------------------------------------------------------------------------
# Cache helpers
# ---------------------------------------------------------------------------

def cache_path(ticker: str, cache_dir: Path) -> Path:
    return cache_dir / f"{ticker}.parquet"


def is_stale(ticker: str, cache_dir: Path, max_stale_days: int) -> bool:
    """Return True when the cached file is absent or older than *max_stale_days*."""
    p = cache_path(ticker, cache_dir)
    if not p.exists():
        return True
    age_days = (datetime.now(tz=timezone.utc).timestamp() - p.stat().st_mtime) / 86400
    return age_days > max_stale_days


# ---------------------------------------------------------------------------
# Supabase upsert
# ---------------------------------------------------------------------------

def upsert_to_supabase(ticker: str, df: pl.DataFrame) -> int:
    """Upsert OHLCV rows to the Supabase ``price_history`` table.

    Returns the number of rows upserted.  Raises ``RuntimeError`` when the
    required environment variables or the ``supabase`` package are missing.
    """
    url = os.environ.get("SUPABASE_URL", "")
    key = os.environ.get("SUPABASE_SERVICE_ROLE_KEY", "")
    if not url or not key:
        raise RuntimeError(
            "SUPABASE_URL and SUPABASE_SERVICE_ROLE_KEY environment variables must be set"
        )

    try:
        from supabase import create_client  # type: ignore[import]
    except ImportError as exc:
        raise RuntimeError(
            "supabase-py is not installed.  Run: pip install supabase"
        ) from exc

    client = create_client(url, key)

    work = df.filter(pl.col("close").is_not_null())
    if work.is_empty():
        return 0

    date_expr = (
        pl.col("date").dt.strftime("%Y-%m-%d")
        if work.schema.get("date") in (pl.Date, pl.Datetime)
        else pl.col("date").cast(pl.Utf8).str.slice(0, 10)
    )
    built = work.select(
        pl.lit(ticker).alias("symbol"),
        date_expr.alias("date"),
        pl.col("open").cast(pl.Float64, strict=False).alias("open"),
        pl.col("high").cast(pl.Float64, strict=False).alias("high"),
        pl.col("low").cast(pl.Float64, strict=False).alias("low"),
        pl.col("close").cast(pl.Float64, strict=False).alias("close"),
        pl.col("volume").cast(pl.Int64, strict=False).alias("volume"),
    )
    rows: list[dict] = built.to_dicts()

    if not rows:
        return 0

    call_with_retry(
        lambda: client.table("price_history").upsert(rows, on_conflict="symbol,date").execute()
    )
    return len(rows)


# ---------------------------------------------------------------------------
# Download
# ---------------------------------------------------------------------------

def _import_yfinance():  # type: ignore[return]
    try:
        import yfinance as yf  # type: ignore[import]

        return yf
    except ImportError:
        print("  yfinance is not installed.  Run: pip install yfinance", file=sys.stderr)
        return None


def download_batch(tickers: list[str], period: str) -> dict[str, pl.DataFrame]:
    """Download *tickers* from Yahoo Finance and return ``{ticker: pl.DataFrame}``.

    Converts the yfinance-returned pandas DataFrame to Polars immediately;
    no pandas operations are performed after that point.
    """
    yf = _import_yfinance()
    if yf is None:
        return {}

    multi = len(tickers) > 1
    raw = yf.download(
        tickers=" ".join(tickers) if multi else tickers[0],
        period=period,
        interval="1d",
        progress=False,
        auto_adjust=True,
        group_by="ticker" if multi else "column",
    )

    results: dict[str, pl.DataFrame] = {}

    for ticker in tickers:
        try:
            sub = raw[ticker] if multi else raw
            if sub is None or sub.empty:
                print(f"    Warning: no data returned for {ticker}", file=sys.stderr)
                continue

            # Bridge pandas → Polars; all subsequent work uses Polars only.
            df = pl.from_pandas(sub.reset_index())

            # Normalise column names
            rename_map = {k: v for k, v in _COL_MAP.items() if k in df.columns}
            if rename_map:
                df = df.rename(rename_map)

            # Drop rows where all OHLC columns are null
            price_cols = [c for c in ("open", "high", "low", "close") if c in df.columns]
            if price_cols:
                df = df.filter(
                    pl.any_horizontal([pl.col(c).is_not_null() for c in price_cols])
                )

            df = df.with_columns(pl.lit(ticker).alias("symbol"))
            results[ticker] = df

        except (
            AttributeError,
            KeyError,
            OSError,
            TypeError,
            ValueError,
            pl.exceptions.ColumnNotFoundError,
            pl.exceptions.ComputeError,
            pl.exceptions.ShapeError,
        ) as exc:
            print(f"    Warning: failed to process {ticker}: {exc}", file=sys.stderr)

    return results


# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------

def main() -> int:  # noqa: C901
    parser = argparse.ArgumentParser(
        description="Pre-load local price-history cache from Yahoo Finance"
    )
    parser.add_argument(
        "--refresh",
        action="store_true",
        help="Skip tickers whose cache file is already fresh",
    )
    parser.add_argument(
        "--max-stale-days",
        type=int,
        default=7,
        metavar="N",
        help="Age threshold in days for considering a cache file stale (default: 7)",
    )
    parser.add_argument(
        "--supabase",
        action="store_true",
        help="Upsert downloaded data to Supabase after caching locally",
    )
    parser.add_argument(
        "--period",
        default=DEFAULT_PERIOD,
        help=f"yfinance period string (default: {DEFAULT_PERIOD})",
    )
    parser.add_argument(
        "--cache-dir",
        type=Path,
        default=DEFAULT_CACHE_DIR,
        metavar="DIR",
        help=f"Local cache directory (default: {DEFAULT_CACHE_DIR})",
    )
    parser.add_argument(
        "--watchlist",
        type=Path,
        default=WATCHLIST_PATH,
        metavar="FILE",
        help=f"Markdown watchlist file (default: {WATCHLIST_PATH})",
    )
    args = parser.parse_args()

    cache_dir: Path = args.cache_dir
    cache_dir.mkdir(parents=True, exist_ok=True)

    print("╔════════════════════════════════════════════╗")
    print("║  preload-history.py — Price History Cache  ║")
    print("╚════════════════════════════════════════════╝")
    print(f"  Cache dir : {cache_dir}")
    print(f"  Period    : {args.period}")
    print()

    watchlist: Path = args.watchlist
    if not watchlist.exists():
        print(f"  Error: watchlist not found at {watchlist}", file=sys.stderr)
        return 1

    tickers = parse_watchlist(watchlist)
    print(f"  Parsed {len(tickers)} tickers from {watchlist.relative_to(REPO_ROOT)}")

    if args.refresh:
        stale = [t for t in tickers if is_stale(t, cache_dir, args.max_stale_days)]
        fresh_count = len(tickers) - len(stale)
        print(
            f"  Refresh mode: {fresh_count} fresh, {len(stale)} stale"
            f" (>{args.max_stale_days}d)"
        )
        to_download = stale
    else:
        to_download = tickers

    if not to_download:
        print("  All tickers are fresh — nothing to do.")
        return 0

    print(f"  Downloading {len(to_download)} tickers ({args.period} history)...")
    print()

    n_batches = math.ceil(len(to_download) / BATCH_SIZE)
    all_frames: dict[str, pl.DataFrame] = {}

    for i in range(n_batches):
        batch = to_download[i * BATCH_SIZE : (i + 1) * BATCH_SIZE]
        print(f"  Batch {i + 1}/{n_batches} ({len(batch)} tickers)...")
        frames = download_batch(batch, args.period)
        all_frames.update(frames)

    # ---- Persist to local cache ----------------------------------------
    saved = 0
    for ticker, df in all_frames.items():
        p = cache_path(ticker, cache_dir)
        df.write_parquet(p)
        saved += 1

    print()
    print(f"  Cached {saved}/{len(to_download)} tickers → {cache_dir}")

    # ---- Optional Supabase upsert ----------------------------------------
    if args.supabase:
        print("  Upserting to Supabase...")
        total_rows = 0
        errors: list[str] = []
        for t, df in all_frames.items():
            try:
                sb_rows = upsert_to_supabase(t, df)
                total_rows += sb_rows
            except (RuntimeError, OSError, ValueError, TypeError, KeyError) as exc:
                errors.append(f"{t}: {exc}")

        print(f"  Upserted {total_rows} rows across {len(all_frames)} tickers")
        if errors:
            for err in errors:
                print(f"  Error — {err}", file=sys.stderr)
            return 1

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
