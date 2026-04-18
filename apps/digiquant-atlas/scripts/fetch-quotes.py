#!/usr/bin/env python3
"""
fetch-quotes.py — Systematic ETF/equity snapshot with technicals
Reads all tickers from config/watchlist.md.  If a local price-history cache
exists (data/price-history/{TICKER}.csv) it loads cached data, fetches only the
missing recent days via yfinance, appends them to the cache, and then computes
technicals over the full cached window.  If no cache exists it falls back to a
plain 3-month download (same as before).

Run  scripts/preload-history.py  once to seed the cache with 2 yr of data.
Afterwards every daily run touches only the latest 1–5 days per ticker.

Usage:
    python3 scripts/fetch-quotes.py                  # today
    python3 scripts/fetch-quotes.py 2026-04-06       # specific date
"""

import argparse
import json
import re
import sys
import time
from datetime import datetime, date, timedelta
from pathlib import Path

import numpy as np
import pandas as pd
import yfinance as yf

ROOT = Path(__file__).parent.parent
CACHE_DIR = ROOT / "data" / "price-history"


# ── helpers ──────────────────────────────────────────────────────────────────

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
    # Exclude table headers and macro-only indicators (fetched by fetch-macro.py)
    EXCLUDE = {"ETF", "DXY", "VIX"}
    # Deduplicate while preserving order
    seen = set()
    result = []
    for t in tickers:
        if t not in seen and t not in EXCLUDE:
            seen.add(t)
            result.append(t)
    return result


def compute_trend(row: dict) -> str:
    sma50 = row.get("sma50")
    sma200 = row.get("sma200")
    price = row.get("price")
    if price is None:
        return "UNKNOWN"
    if sma50 and sma200:
        if price > sma50 > sma200:
            return "UPTREND"
        if price < sma50 < sma200:
            return "DOWNTREND"
    if sma50:
        return "ABOVE50" if price > sma50 else "BELOW50"
    return "NEUTRAL"


def safe_float(val, decimals: int = 2):
    """Convert pandas scalar to a plain Python float, or None if NaN/inf."""
    try:
        f = float(val)
        if pd.isna(f) or not np.isfinite(f):
            return None
        return round(f, decimals)
    except (TypeError, ValueError):
        return None


# ── price-history cache ──────────────────────────────────────────────────────

def _cache_path(ticker: str) -> Path:
    return CACHE_DIR / f"{ticker}.csv"


def load_cached(ticker: str) -> pd.DataFrame | None:
    """Load cached OHLCV CSV for *ticker*. Returns None when no cache exists."""
    p = _cache_path(ticker)
    if not p.exists():
        return None
    try:
        df = pd.read_csv(p, parse_dates=["Date"], index_col="Date")
        if df.empty:
            return None
        return df.sort_index()
    except Exception:
        return None


def save_cached(ticker: str, df: pd.DataFrame) -> None:
    """Persist (or update) the cache CSV for *ticker*."""
    CACHE_DIR.mkdir(parents=True, exist_ok=True)
    df = df.sort_index()
    df.columns = [c.capitalize() for c in df.columns]
    df.index.name = "Date"
    dest = _cache_path(ticker)
    tmp = dest.with_suffix(".csv.tmp")
    df.to_csv(tmp, date_format="%Y-%m-%d")
    tmp.rename(dest)


def incremental_fetch(tickers: list[str]) -> dict[str, pd.DataFrame]:
    """For each ticker: load cache → fetch only missing days → merge & save.

    Tickers *without* a cache are collected and bulk-downloaded (3 mo) in a
    single yf.download call so we stay fast even on first run.  Tickers that
    *have* a cache are collected by how many calendar days they're behind and
    fetched in small date-ranged batches.
    """
    uncached: list[str] = []
    cached_work: list[tuple[str, pd.DataFrame, str]] = []  # (ticker, df, start_str)

    for t in tickers:
        df = load_cached(t)
        if df is None:
            uncached.append(t)
        else:
            last_date = df.index.max()
            start = (last_date + timedelta(days=1)).strftime("%Y-%m-%d")
            cached_work.append((t, df, start))

    result: dict[str, pd.DataFrame] = {}

    # ── uncached: bulk 3-month download (same as legacy behaviour) ───────
    if uncached:
        print(f"  No cache for {len(uncached)} tickers — downloading 3mo bulk...")
        BATCH = 25
        for i in range(0, len(uncached), BATCH):
            batch = uncached[i:i + BATCH]
            data = fetch_batch(batch, period="3mo")
            for t, df in data.items():
                save_cached(t, df)
                result[t] = df
            if i + BATCH < len(uncached):
                time.sleep(0.5)

    # ── cached: incremental update ───────────────────────────────────────
    if cached_work:
        today_str = date.today().strftime("%Y-%m-%d")
        to_fetch = [(t, df, s) for t, df, s in cached_work if s <= today_str]
        already_current = len(cached_work) - len(to_fetch)
        if already_current:
            print(f"  {already_current} tickers already up-to-date in cache")
        if to_fetch:
            print(f"  Incremental update for {len(to_fetch)} cached tickers...")
            # Group tickers to download them together
            fetch_tickers = [t for t, _, _ in to_fetch]
            earliest_start = min(s for _, _, s in to_fetch)
            try:
                raw = yf.download(
                    fetch_tickers,
                    start=earliest_start,
                    progress=False,
                    threads=True,
                )
                for t, old_df, start_str in to_fetch:
                    try:
                        if isinstance(raw.columns, pd.MultiIndex):
                            new_df = raw.xs(t, level=1, axis=1).copy().dropna(how="all")
                        elif len(fetch_tickers) == 1:
                            new_df = raw.copy().dropna(how="all")
                        else:
                            new_df = pd.DataFrame()
                        if not new_df.empty:
                            merged = pd.concat([old_df, new_df])
                            merged = merged[~merged.index.duplicated(keep="last")]
                            merged = merged.sort_index()
                        else:
                            merged = old_df
                        save_cached(t, merged)
                        result[t] = merged
                    except Exception:
                        result[t] = old_df
            except Exception as e:
                print(f"    ⚠️  incremental download failed: {e}")
                for t, old_df, _ in to_fetch:
                    result[t] = old_df

        # Tickers that were already current still need to be in result
        for t, df, s in cached_work:
            if t not in result:
                result[t] = df

    return result


def fetch_batch(tickers: list[str], period: str = "3mo") -> dict[str, pd.DataFrame]:
    """Download OHLCV for a batch of tickers. Returns dict ticker → DataFrame."""
    if not tickers:
        return {}
    try:
        raw = yf.download(tickers, period=period, progress=False, threads=True)
        result = {}
        if isinstance(raw.columns, pd.MultiIndex):
            for t in tickers:
                try:
                    df = raw.xs(t, level=1, axis=1).copy()
                    df = df.dropna(how="all")
                    result[t] = df
                except KeyError:
                    pass
        else:
            # Single ticker
            df = raw.copy().dropna(how="all")
            result[tickers[0]] = df
        return result
    except Exception as e:
        print(f"  ⚠️  batch download failed: {e}")
        return {}


def build_snapshot(ticker: str, df: pd.DataFrame) -> dict:
    """Compute technicals for a single ticker's OHLCV DataFrame."""
    if df is None or df.empty or len(df) < 5:
        return {"ticker": ticker, "error": "insufficient_data"}

    try:
        import pandas_ta as ta
    except ImportError:
        # numba doesn't support Python 3.14 — mock it so pandas-ta loads without JIT
        import types as _t
        _numba = _t.ModuleType("numba")
        _numba.njit = lambda f=None, **kw: f if f else (lambda fn: fn)
        sys.modules.setdefault("numba", _numba)
        try:
            import pandas_ta as ta
        except ImportError:
            print("  ⚠️  pandas-ta not installed — run: pip install pandas-ta")
            return {"ticker": ticker, "error": "pandas_ta_missing"}

    # Normalise column names
    df.columns = [c.lower() for c in df.columns]
    required = {"open", "high", "low", "close", "volume"}
    if not required.issubset(set(df.columns)):
        return {"ticker": ticker, "error": "missing_ohlcv_columns"}

    df = df.sort_index()

    # Compute indicators
    df.ta.rsi(length=14, append=True)
    df.ta.macd(fast=12, slow=26, signal=9, append=True)
    df.ta.sma(length=20, append=True)
    df.ta.sma(length=50, append=True)
    df.ta.sma(length=200, append=True)
    df.ta.atr(length=14, append=True)
    df.ta.bbands(length=20, std=2, append=True)

    row = df.iloc[-1]
    prev = df.iloc[-2] if len(df) >= 2 else row

    price = safe_float(row.get("close"))
    prev_close = safe_float(prev.get("close"))
    pct_1d = round((price - prev_close) / prev_close * 100, 2) if price and prev_close and prev_close > 0 else None

    # 52-week high/low (accurate when cache has ≥1yr; otherwise uses whatever window is available)
    high_range = safe_float(df["high"].max())
    low_range = safe_float(df["low"].min())
    pct_from_high = round((price - high_range) / high_range * 100, 2) if price and high_range and high_range > 0 else None

    # Volume ratio vs 20-day average
    avg_vol_20 = safe_float(df["volume"].tail(20).mean(), 0)
    today_vol = safe_float(row.get("volume"), 0)
    volume_ratio = round(today_vol / avg_vol_20, 2) if avg_vol_20 and avg_vol_20 > 0 else None

    sma50 = safe_float(row.get("SMA_50"))
    sma200 = safe_float(row.get("SMA_200"))
    rsi = safe_float(row.get("RSI_14"))

    # MACD cross signal
    macd_hist = safe_float(row.get("MACDh_12_26_9"))
    prev_macd_hist = safe_float(prev.get("MACDh_12_26_9"))
    if macd_hist is not None and prev_macd_hist is not None:
        if macd_hist > 0 and prev_macd_hist <= 0:
            macd_signal = "BULLISH_CROSS"
        elif macd_hist < 0 and prev_macd_hist >= 0:
            macd_signal = "BEARISH_CROSS"
        elif macd_hist > 0:
            macd_signal = "BULLISH"
        else:
            macd_signal = "BEARISH"
    else:
        macd_signal = None

    snap = {
        "ticker": ticker,
        "price": price,
        "pct_1d": pct_1d,
        "high_range": high_range,
        "low_range": low_range,
        "pct_from_high": pct_from_high,
        "volume": today_vol,
        "volume_ratio": volume_ratio,
        "rsi14": rsi,
        "macd_signal": macd_signal,
        "macd_hist": macd_hist,
        "sma20": safe_float(row.get("SMA_20")),
        "sma50": sma50,
        "sma200": sma200,
        "atr14": safe_float(row.get("ATRr_14")),
        "bb_upper": safe_float(row.get("BBU_20_2.0")),
        "bb_lower": safe_float(row.get("BBL_20_2.0")),
        "above_sma50": bool(price > sma50) if price and sma50 else None,
        "above_sma200": bool(price > sma200) if price and sma200 else None,
        "trend": None,  # filled below
    }
    snap["trend"] = compute_trend(snap)
    return snap


def rsi_label(rsi) -> str:
    if rsi is None:
        return "–"
    if rsi >= 70:
        return f"{rsi:.0f} ⚠️"
    if rsi <= 35:
        return f"{rsi:.0f} 🟡"
    return f"{rsi:.0f}"


def trend_emoji(trend: str) -> str:
    return {"UPTREND": "↑", "DOWNTREND": "↓", "ABOVE50": "↗", "BELOW50": "↘", "NEUTRAL": "→", "UNKNOWN": "–"}.get(trend, "–")


def write_summary_md(snapshots: list[dict], output_path: Path, fetched_at: str):
    """Write a human-readable markdown summary of all quotes."""
    valid = [s for s in snapshots if "error" not in s and s.get("price")]
    errors = [s for s in snapshots if "error" in s]

    # Sort by 1D% descending
    valid_sorted = sorted(valid, key=lambda x: x.get("pct_1d") or 0, reverse=True)

    # Classify into buckets
    bullish = [s for s in valid if s.get("trend") in ("UPTREND",) and (s.get("rsi14") or 0) < 70]
    caution = [s for s in valid if s.get("trend") in ("ABOVE50", "NEUTRAL") or (s.get("rsi14") or 0) >= 70]
    bearish = [s for s in valid if s.get("trend") in ("DOWNTREND", "BELOW50")]

    lines = [
        f"# Quotes Snapshot — {fetched_at}",
        "",
        f"> **{len(valid)}** tickers fetched successfully. {len(errors)} failed.",
        f"> Freshness: ~15min delayed (Yahoo Finance). Technicals computed from cached OHLCV history.",
        "",
        "---",
        "",
        "## Overview Buckets",
        "",
        f"| Bucket | Count | Tickers |",
        f"|--------|-------|---------|",
        f"| ↑ UPTREND | {len(bullish)} | {', '.join(s['ticker'] for s in bullish[:12])}{'…' if len(bullish) > 12 else ''} |",
        f"| ↗/→ MIXED | {len(caution)} | {', '.join(s['ticker'] for s in caution[:12])}{'…' if len(caution) > 12 else ''} |",
        f"| ↓ DOWNTREND | {len(bearish)} | {', '.join(s['ticker'] for s in bearish[:12])}{'…' if len(bearish) > 12 else ''} |",
        "",
        "---",
        "",
        "## Full Quotes Table",
        "",
        "| Ticker | Price | 1D% | Trend | RSI14 | MACD | vs SMA50 | vs SMA200 | Vol Ratio | ATR14 |",
        "|--------|-------|-----|-------|-------|------|----------|-----------|-----------|-------|",
    ]

    for s in valid_sorted:
        p = s.get("price", "–")
        pct = f"{s['pct_1d']:+.2f}%" if s.get("pct_1d") is not None else "–"
        trend = f"{trend_emoji(s['trend'])} {s['trend']}" if s.get("trend") else "–"
        rsi = rsi_label(s.get("rsi14"))
        macd = s.get("macd_signal", "–") or "–"
        sma50_flag = "✅" if s.get("above_sma50") else ("❌" if s.get("above_sma50") is False else "–")
        sma200_flag = "✅" if s.get("above_sma200") else ("❌" if s.get("above_sma200") is False else "–")
        vol = f"{s['volume_ratio']:.1f}×" if s.get("volume_ratio") is not None else "–"
        atr = f"{s['atr14']:.2f}" if s.get("atr14") is not None else "–"

        lines.append(f"| {s['ticker']} | {p} | {pct} | {trend} | {rsi} | {macd} | {sma50_flag} | {sma200_flag} | {vol} | {atr} |")

    if errors:
        lines += ["", "---", "", "## Fetch Errors", ""]
        for s in errors:
            lines.append(f"- **{s['ticker']}**: {s['error']}")

    lines += [
        "",
        "---",
        "",
        "## Signal Legend",
        "",
        "- **Trend**: UPTREND = price > SMA50 > SMA200 | DOWNTREND = price < SMA50 < SMA200",
        "- **RSI**: ⚠️ = overbought (≥70) | 🟡 = oversold (≤35)",
        "- **MACD**: BULLISH_CROSS / BEARISH_CROSS = histogram crossed zero today",
        "- **vs SMA50/200**: ✅ above | ❌ below",
        "- **Vol Ratio**: today's volume ÷ 20-day average (>1.3 = elevated)",
        "- **ATR14**: 14-day Average True Range (dollar volatility measure)",
    ]

    output_path.write_text("\n".join(lines) + "\n", encoding="utf-8")


# ── main ─────────────────────────────────────────────────────────────────────

def main():
    parser = argparse.ArgumentParser(
        description="fetch-quotes.py — Systematic ETF/equity snapshot with technicals",
        epilog="Reads all tickers from config/watchlist.md. Uses local CSV cache when available."
    )
    parser.add_argument(
        "date", nargs="?", default=date.today().strftime("%Y-%m-%d"),
        metavar="YYYY-MM-DD", help="Target date (default: today)"
    )
    args = parser.parse_args()
    target_date = args.date
    fetched_at = datetime.now().strftime("%Y-%m-%d %H:%M ET")

    out_dir = ROOT / "data" / "agent-cache" / "daily" / target_date / "data"
    out_dir.mkdir(parents=True, exist_ok=True)

    print(f"fetch-quotes.py — {target_date}")
    print("  Parsing watchlist tickers...")
    tickers = parse_tickers_from_watchlist()
    print(f"  Found {len(tickers)} tickers")

    # ── load from cache + incremental update (or bulk 3mo fallback) ──────
    all_ohlcv = incremental_fetch(tickers)

    print(f"  Computing technicals for {len(all_ohlcv)} tickers...")
    snapshots = []
    for ticker in tickers:
        df = all_ohlcv.get(ticker)
        snap = build_snapshot(ticker, df)
        snapshots.append(snap)

    # Build output JSON
    output = {
        "date": target_date,
        "fetched_at": fetched_at,
        "ticker_count": len(tickers),
        "success_count": sum(1 for s in snapshots if "error" not in s),
        "snapshots": snapshots,
    }

    quotes_json = out_dir / "quotes.json"
    quotes_json.write_text(json.dumps(output, indent=2, default=str), encoding="utf-8")
    print(f"  ✅ Wrote {quotes_json}")

    quotes_md = out_dir / "quotes-summary.md"
    write_summary_md(snapshots, quotes_md, fetched_at)
    print(f"  ✅ Wrote {quotes_md}")

    success = sum(1 for s in snapshots if "error" not in s)
    failed = [s for s in snapshots if "error" in s]
    errors = len(failed)
    if failed:
        for s in failed:
            print(f"  ⚠️  {s['ticker']}: {s['error']}", file=sys.stderr)
    print(f"  Done — {success} OK, {errors} errors")


if __name__ == "__main__":
    main()
