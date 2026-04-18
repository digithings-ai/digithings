#!/usr/bin/env python3
"""
preload-history.py — Bulk download and cache OHLCV price history for all watchlist tickers.
One-time setup (or periodic refresh). Daily pipeline then only appends latest quotes.

Storage: data/price-history/{TICKER}.csv   (one CSV per ticker)

Usage:
    python3 scripts/preload-history.py                  # all watchlist, 2y history
    python3 scripts/preload-history.py --period 5y      # all watchlist, 5y
    python3 scripts/preload-history.py --ticker SPY     # single ticker only
    python3 scripts/preload-history.py --refresh        # re-fetch tickers whose cache is >7d stale
    python3 scripts/preload-history.py --supabase --supabase-sync   # daily: gap-fill + new-ticker backfill
"""

import argparse
import os
import re
import sys
import time
from collections import defaultdict
from datetime import date, datetime, timedelta, timezone
from pathlib import Path

import pandas as pd
import yfinance as yf

ROOT = Path(__file__).parent.parent
CACHE_DIR = ROOT / "data" / "price-history"

# Keep non-watchlist “dashboard benchmarks” synced to Supabase even if the
# research watchlist doesn’t include them yet (Overview top assets, comparables).
# These must be valid Yahoo Finance symbols.
EXTRA_DASHBOARD_TICKERS: list[str] = [
    "DIA",
    "VTI",
    "AGG",
    "UUP",
    "BITO",
]


# ── ticker parsing (shared with fetch-quotes.py) ────────────────────────────

def parse_tickers_from_watchlist() -> list[str]:
    """Extract all uppercase ticker symbols from config/watchlist.md table rows."""
    wl = ROOT / "config" / "watchlist.md"
    if not wl.exists():
        print("  ⚠️  config/watchlist.md not found — using fallback universe")
        return ["SPY", "QQQ", "IWM", "XLK", "XLF", "XLE", "XLV", "XLI",
                "XLRE", "XLU", "XLY", "XLP", "XLB", "XLC", "TLT", "GLD",
                "IAU", "SLV", "USO", "DBO", "IBIT", "FBTC", "BIL", "SHY",
                "EFA", "EEM", "FXI", "EWJ", "EWZ"]
    text = wl.read_text(encoding="utf-8")
    # Match tickers: plain uppercase (SPY), hyphenated crypto (BTC-USD),
    # or alphanumeric yfinance IDs (SUI20947-USD)
    tickers = re.findall(r"^\|\s*([A-Z][A-Z0-9]{1,9}(?:-[A-Z]{2,4})?)\s*\|", text, re.MULTILINE)
    # Exclude table headers and macro-only indicators
    EXCLUDE = {"ETF", "DXY", "VIX"}
    seen = set()
    result = []
    for t in tickers:
        if t not in seen and t not in EXCLUDE:
            seen.add(t)
            result.append(t)
    return result


# ── cache helpers ────────────────────────────────────────────────────────────

def cache_path(ticker: str) -> Path:
    return CACHE_DIR / f"{ticker}.csv"


def cache_is_stale(ticker: str, max_age_days: int = 7) -> bool:
    """True if cache file doesn't exist or its most recent data row is older than max_age_days."""
    p = cache_path(ticker)
    if not p.exists():
        return True
    try:
        df = pd.read_csv(p, parse_dates=["Date"], index_col="Date")
        if df.empty:
            return True
        last_date = df.index.max()
        return (datetime.now() - last_date.to_pydatetime()).days > max_age_days
    except Exception:
        return True


def save_cache(ticker: str, df: pd.DataFrame) -> None:
    """Save OHLCV DataFrame to CSV cache. Index must be DatetimeIndex named 'Date'."""
    CACHE_DIR.mkdir(parents=True, exist_ok=True)
    df = df.sort_index()
    # Ensure consistent column names
    df.columns = [c.capitalize() for c in df.columns]
    df.index.name = "Date"
    dest = cache_path(ticker)
    tmp = dest.with_suffix(".csv.tmp")
    df.to_csv(tmp, date_format="%Y-%m-%d")
    tmp.rename(dest)


def upsert_to_supabase(ticker: str, df: pd.DataFrame) -> int:
    """Upsert OHLCV rows for a single ticker into the Supabase price_history table.

    Returns the number of rows upserted, or 0 on error.
    Requires SUPABASE_URL and SUPABASE_SERVICE_KEY environment variables.
    """
    try:
        from supabase import create_client
    except ImportError:
        print("    ⚠️  supabase-py not installed — pip install supabase")
        return 0

    # Load .env if present
    try:
        from dotenv import load_dotenv
        load_dotenv(ROOT / "config" / "supabase.env")
    except ImportError:
        pass

    url = os.environ.get("SUPABASE_URL")
    key = os.environ.get("SUPABASE_SERVICE_KEY")
    if not url or not key:
        print("    ⚠️  SUPABASE_URL / SUPABASE_SERVICE_KEY not set — skipping Supabase upsert")
        return 0

    sb = create_client(url, key)

    df = df.copy()
    df.index.name = "Date"
    df = df.sort_index()
    col_map = {c: c.capitalize() for c in df.columns}
    df = df.rename(columns=col_map)

    rows = []
    for date_idx, row in df.iterrows():
        rows.append({
            "date": date_idx.strftime("%Y-%m-%d") if hasattr(date_idx, "strftime") else str(date_idx)[:10],
            "ticker": ticker,
            "open": float(row["Open"]) if "Open" in row and pd.notna(row["Open"]) else None,
            "high": float(row["High"]) if "High" in row and pd.notna(row["High"]) else None,
            "low": float(row["Low"]) if "Low" in row and pd.notna(row["Low"]) else None,
            "close": float(row["Close"]) if "Close" in row and pd.notna(row["Close"]) else None,
            "volume": int(row["Volume"]) if "Volume" in row and pd.notna(row["Volume"]) else None,
        })
        # Drop rows where close is None (required column)
    rows = [r for r in rows if r["close"] is not None]

    if not rows:
        return 0

    # Upsert in chunks (and retry transient 5xx/502 gateway errors).
    CHUNK = 200
    total = 0
    for i in range(0, len(rows), CHUNK):
        chunk = rows[i : i + CHUNK]
        for attempt in range(1, 6):
            try:
                sb.table("price_history").upsert(chunk).execute()
                total += len(chunk)
                break
            except Exception as e:
                if attempt >= 5:
                    print(f"    ⚠️  Supabase upsert failed for {ticker} chunk {i // CHUNK + 1}: {e}")
                    break
                time.sleep(0.75 * attempt)
    return total


# ── download ─────────────────────────────────────────────────────────────────

def download_full_history(tickers: list[str], period: str = "2y",
                          batch_size: int = 25) -> dict[str, pd.DataFrame]:
    """Download OHLCV for tickers in batches. Returns dict ticker → DataFrame."""
    batches = [tickers[i:i + batch_size] for i in range(0, len(tickers), batch_size)]
    result: dict[str, pd.DataFrame] = {}

    for i, batch in enumerate(batches, 1):
        print(f"  Batch {i}/{len(batches)} ({len(batch)} tickers)...")
        try:
            raw = yf.download(batch, period=period, progress=False, threads=True)
            if raw.empty:
                continue
            if isinstance(raw.columns, pd.MultiIndex):
                for t in batch:
                    try:
                        df = raw.xs(t, level=1, axis=1).copy()
                        df = df.dropna(how="all")
                        if not df.empty:
                            result[t] = df
                    except KeyError:
                        pass
            else:
                # Single ticker
                df = raw.copy().dropna(how="all")
                if not df.empty:
                    result[batch[0]] = df
        except Exception as e:
            print(f"    ⚠️  Batch {i} failed: {e}")
        if i < len(batches):
            time.sleep(0.5)

    return result


def download_date_range(
    tickers: list[str],
    start: date,
    end_exclusive: date,
    batch_size: int = 25,
) -> dict[str, pd.DataFrame]:
    """Download OHLCV for tickers for [start, end_exclusive). yfinance `end` is exclusive."""
    if not tickers:
        return {}
    batches = [tickers[i : i + batch_size] for i in range(0, len(tickers), batch_size)]
    result: dict[str, pd.DataFrame] = {}
    start_s = start.strftime("%Y-%m-%d")
    end_s = end_exclusive.strftime("%Y-%m-%d")

    for i, batch in enumerate(batches, 1):
        print(f"  Batch {i}/{len(batches)} ({len(batch)} tickers) {start_s} … {end_s} …")
        try:
            raw = yf.download(batch, start=start_s, end=end_s, progress=False, threads=True)
            if raw.empty:
                continue
            if isinstance(raw.columns, pd.MultiIndex):
                for t in batch:
                    try:
                        df = raw.xs(t, level=1, axis=1).copy()
                        df = df.dropna(how="all")
                        if not df.empty:
                            result[t] = df
                    except KeyError:
                        pass
            else:
                df = raw.copy().dropna(how="all")
                if not df.empty:
                    result[batch[0]] = df
        except Exception as e:
            print(f"    ⚠️  Batch {i} failed: {e}")
        if i < len(batches):
            time.sleep(0.5)

    return result


def _yahoo_to_ohlcv(df: pd.DataFrame) -> pd.DataFrame:
    """Normalize yfinance frame to Open/High/Low/Close/Volume with naive date index."""
    if df.empty:
        return df
    out = df.copy()
    out.index = pd.to_datetime(out.index).tz_localize(None)
    out.columns = [str(c).capitalize() for c in out.columns]
    cols = [c for c in ["Open", "High", "Low", "Close", "Volume"] if c in out.columns]
    return out[cols].dropna(how="all")


def _supabase_rows_to_df(rows: list[dict]) -> pd.DataFrame:
    if not rows:
        return pd.DataFrame()
    df = pd.DataFrame(rows)
    df["date"] = pd.to_datetime(df["date"])
    df = df.set_index("date")
    df = df.rename(
        columns={
            "open": "Open",
            "high": "High",
            "low": "Low",
            "close": "Close",
            "volume": "Volume",
        }
    )
    for c in ["Open", "High", "Low", "Close", "Volume"]:
        if c not in df.columns:
            df[c] = float("nan")
    return df[["Open", "High", "Low", "Close", "Volume"]]


def _merge_ohlcv(old: pd.DataFrame, new: pd.DataFrame) -> pd.DataFrame:
    if old is None or old.empty:
        return new.sort_index() if new is not None and not new.empty else pd.DataFrame()
    if new is None or new.empty:
        return old.sort_index()
    merged = pd.concat([old, new])
    merged = merged[~merged.index.duplicated(keep="last")]
    return merged.sort_index()


def _get_supabase_client():
    try:
        from supabase import create_client
    except ImportError:
        print("  ⚠️  supabase-py not installed — pip install supabase")
        return None
    try:
        from dotenv import load_dotenv
        load_dotenv(ROOT / "config" / "supabase.env")
    except ImportError:
        pass
    url = os.environ.get("SUPABASE_URL")
    key = os.environ.get("SUPABASE_SERVICE_KEY")
    if not url or not key:
        print("  ⚠️  SUPABASE_URL / SUPABASE_SERVICE_KEY not set")
        return None
    return create_client(url, key)


def _latest_date_supabase(sb, ticker: str) -> date | None:
    r = (
        sb.table("price_history")
        .select("date")
        .eq("ticker", ticker)
        .order("date", desc=True)
        .limit(1)
        .execute()
    )
    if not r.data:
        return None
    d = r.data[0]["date"]
    if isinstance(d, str):
        return date.fromisoformat(d[:10])
    if hasattr(d, "date") and callable(getattr(d, "date", None)):
        return d.date()
    return None


def _load_price_history_supabase(sb, ticker: str) -> pd.DataFrame:
    """Full series for one ticker (paginated)."""
    page = 1000
    offset = 0
    rows: list[dict] = []
    while True:
        r = (
            sb.table("price_history")
            .select("date,open,high,low,close,volume")
            .eq("ticker", ticker)
            .order("date")
            .range(offset, offset + page - 1)
            .execute()
        )
        chunk = r.data or []
        if not chunk:
            break
        rows.extend(chunk)
        if len(chunk) < page:
            break
        offset += page
    return _supabase_rows_to_df(rows)


def run_supabase_sync(new_ticker_period: str) -> None:
    """Gap-fill each watchlist ticker to UTC today; full-history fetch if no rows in Supabase."""
    sb = _get_supabase_client()
    if sb is None:
        sys.exit(1)

    tickers = parse_tickers_from_watchlist()
    base = len(tickers)
    # Ensure dashboard tickers are present (no duplicates).
    for t in EXTRA_DASHBOARD_TICKERS:
        if t not in tickers:
            tickers.append(t)
    if len(tickers) != base:
        print(f"  Parsed {base} tickers from config/watchlist.md (+{len(tickers) - base} dashboard extras)")
    else:
        print(f"  Parsed {len(tickers)} tickers from config/watchlist.md")

    # Use the most recent *complete* UTC day for daily bars. If we try to fetch
    # today's bar before Yahoo has published it, yfinance emits noisy
    # "possibly delisted" errors and can sometimes hang.
    utc_today = datetime.now(timezone.utc).date()
    end_exclusive = utc_today

    new_tickers: list[str] = []
    gaps: dict[tuple[date, date], list[str]] = defaultdict(list)

    for t in tickers:
        latest = _latest_date_supabase(sb, t)
        if latest is None:
            new_tickers.append(t)
            continue
        start = latest + timedelta(days=1)
        if start >= end_exclusive:
            print(f"    ⏭️  {t:6s}  up to date (latest {latest})")
            continue
        gaps[(start, end_exclusive)].append(t)

    sb_total = 0
    saved = 0

    # New symbols: pull as much history as Yahoo allows (default max).
    if new_tickers:
        print(f"\n  New tickers (no price_history): {len(new_tickers)} — period={new_ticker_period}")
        print()
        data = download_full_history(new_tickers, period=new_ticker_period)
        for t in new_tickers:
            df = data.get(t)
            if df is not None and not df.empty:
                df = _yahoo_to_ohlcv(df)
                if not df.empty:
                    save_cache(t, df)
                    sb_rows = upsert_to_supabase(t, df)
                    sb_total += sb_rows
                    saved += 1
                    print(
                        f"    ✅ {t:6s}  {len(df):>4d} rows  "
                        f"{df.index.min().strftime('%Y-%m-%d')} → {df.index.max().strftime('%Y-%m-%d')}  "
                        f"↑Supabase {sb_rows}r"
                    )
                else:
                    print(f"    ❌ {t:6s}  empty after normalize")
            else:
                print(f"    ❌ {t:6s}  no data returned")

    # Existing: fetch [latest+1, today] and merge with Supabase history.
    for (start, end_ex), group in sorted(gaps.items()):
        print(f"\n  Gap-fill {len(group)} tickers  {start} → {end_ex} (exclusive end)")
        print()
        raw = download_date_range(group, start, end_ex)
        for t in group:
            old_df = _load_price_history_supabase(sb, t)
            new_raw = raw.get(t)
            if new_raw is None or new_raw.empty:
                print(f"    ⚠️  {t:6s}  no new Yahoo rows — leaving DB/cache as-is")
                if not old_df.empty:
                    save_cache(t, old_df)
                continue
            new_df = _yahoo_to_ohlcv(new_raw)
            if new_df.empty:
                print(f"    ⚠️  {t:6s}  empty after normalize")
                continue
            new_df = new_df[new_df.index >= pd.Timestamp(start)]
            merged = _merge_ohlcv(old_df, new_df)
            if merged.empty:
                print(f"    ❌ {t:6s}  merge empty")
                continue
            save_cache(t, merged)
            sb_rows = upsert_to_supabase(t, new_df) if not new_df.empty else 0
            sb_total += sb_rows
            saved += 1
            print(
                f"    ✅ {t:6s}  cache {len(merged):>4d} rows  "
                f"{merged.index.min().strftime('%Y-%m-%d')} → {merged.index.max().strftime('%Y-%m-%d')}  "
                f"  ↑Supabase +{sb_rows}r"
            )

    print()
    print(f"  Synced {saved} tickers; upserted {sb_total} rows to Supabase price_history")
    print("  Done.")


# ── main ─────────────────────────────────────────────────────────────────────

def main():
    parser = argparse.ArgumentParser(description="Preload OHLCV price history cache")
    parser.add_argument("--period", default="2y",
                        help="yfinance period string: 1y, 2y, 5y, max (default: 2y)")
    parser.add_argument("--ticker", default=None,
                        help="Fetch a single ticker instead of the full watchlist")
    parser.add_argument("--refresh", action="store_true",
                        help="Only re-fetch tickers whose cache is >7 days stale")
    parser.add_argument("--max-stale-days", type=int, default=7,
                        help="Staleness threshold for --refresh mode (default: 7)")
    parser.add_argument("--supabase", action="store_true",
                        help="Also upsert fetched data to Supabase price_history table")
    parser.add_argument(
        "--supabase-sync",
        action="store_true",
        help="Watchlist only: use latest Supabase date per ticker to gap-fill to UTC today, "
        "or fetch full history (see --new-ticker-period) when no rows exist. Implies --supabase.",
    )
    parser.add_argument(
        "--new-ticker-period",
        default="max",
        help="yfinance period for tickers with no price_history rows (default: max)",
    )
    args = parser.parse_args()

    if args.supabase_sync:
        if args.refresh:
            parser.error("--supabase-sync cannot be combined with --refresh")
        if args.ticker:
            parser.error("--supabase-sync cannot be combined with --ticker")
        args.supabase = True

    CACHE_DIR.mkdir(parents=True, exist_ok=True)

    print("╔════════════════════════════════════════════╗")
    print("║  preload-history.py — Price History Cache  ║")
    print("╚════════════════════════════════════════════╝")
    print(f"  Cache dir : {CACHE_DIR}")
    if args.supabase_sync:
        print("  Mode      : supabase-sync (gap-fill + new-ticker backfill)")
        print(f"  New tickers use period: {args.new_ticker_period}")
    else:
        print(f"  Period    : {args.period}")
    print()

    if args.supabase_sync:
        run_supabase_sync(args.new_ticker_period)
        return

    # Determine ticker list
    if args.ticker:
        tickers = [args.ticker.upper()]
    else:
        tickers = parse_tickers_from_watchlist()
        print(f"  Parsed {len(tickers)} tickers from config/watchlist.md")

    # Filter if refresh mode
    if args.refresh and not args.ticker:
        stale = [t for t in tickers if cache_is_stale(t, args.max_stale_days)]
        fresh = len(tickers) - len(stale)
        print(f"  Refresh mode: {fresh} fresh, {len(stale)} stale (>{args.max_stale_days}d)")
        if not stale:
            print("  ✅ All tickers are fresh — nothing to do.")
            return
        tickers = stale

    print(f"  Downloading {len(tickers)} tickers ({args.period} history)...")
    print()

    data = download_full_history(tickers, period=args.period)

    saved = 0
    sb_total = 0
    for t in tickers:
        df = data.get(t)
        if df is not None and not df.empty:
            save_cache(t, df)
            rows = len(df)
            first = df.index.min().strftime("%Y-%m-%d")
            last = df.index.max().strftime("%Y-%m-%d")
            sb_note = ""
            if args.supabase:
                sb_rows = upsert_to_supabase(t, df)
                sb_note = f"  ↑Supabase {sb_rows}r" if sb_rows else "  ↑skip"
                sb_total += sb_rows
            print(f"    ✅ {t:6s}  {rows:>4d} rows  {first} → {last}{sb_note}")
            saved += 1
        else:
            print(f"    ❌ {t:6s}  no data returned")

    print()
    print(f"  Cached {saved}/{len(tickers)} tickers to {CACHE_DIR}")
    if args.supabase:
        print(f"  Upserted {sb_total} rows to Supabase price_history")
    print("  Done.")


if __name__ == "__main__":
    main()
