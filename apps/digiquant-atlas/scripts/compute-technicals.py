#!/usr/bin/env python3
"""
compute-technicals.py — Compute multi-timeframe TA indicators from price history.

Reads OHLCV from the local CSV cache (data/price-history/), computes 35+ indicators
across trend, momentum, volatility, and mean-reversion dimensions, then upserts
results to the Supabase price_technicals table.

Indicator coverage:
  Trend           SMA 20/50/200, EMA 12/26/50, price-vs-MA %
  Trend Strength  ADX 14, +DI / -DI (directional movement index)
  Momentum        RSI 7/14/21, MACD 12-26-9, ROC 5/10/21
  Volatility      ATR 14 (abs + %), Bollinger Bands 20/2 (upper/mid/lower/%B/bandwidth)
                  21-day realized volatility (annualized)
  Mean Reversion  Stochastic %K/%D, Z-score vs SMA50, Z-score vs SMA200

Usage:
    python3 scripts/compute-technicals.py                    # all tickers, last 365 days
    python3 scripts/compute-technicals.py --all              # full 5yr history backfill
    python3 scripts/compute-technicals.py --ticker GLD       # single ticker
    python3 scripts/compute-technicals.py --days 30          # last 30 rows only
    python3 scripts/compute-technicals.py --supabase         # upsert to Supabase
"""

import argparse
import os
import re
import sys
import time
from pathlib import Path

import numpy as np
import pandas as pd

ROOT = Path(__file__).parent.parent
CACHE_DIR = ROOT / "data" / "price-history"

# Minimum bars needed before we compute (prevents nonsense values at the start)
MIN_BARS = 30


# ── helpers ───────────────────────────────────────────────────────────────────

def _ta():
    """Lazy-import pandas_ta, working around numba incompatibility on Python 3.14+."""
    try:
        import pandas_ta as _ta_mod
        return _ta_mod
    except ImportError:
        pass
    import types as _t
    _numba = _t.ModuleType("numba")
    _numba.njit = lambda f=None, **kw: f if f else (lambda fn: fn)
    sys.modules.setdefault("numba", _numba)
    import pandas_ta as _ta_mod
    return _ta_mod


def safe_float(val, decimals: int = 4):
    """Return a rounded Python float, or None for NaN / inf."""
    try:
        f = float(val)
        return None if (pd.isna(f) or not np.isfinite(f)) else round(f, decimals)
    except (TypeError, ValueError):
        return None


def parse_tickers_from_watchlist() -> list[str]:
    wl = ROOT / "config" / "watchlist.md"
    if not wl.exists():
        return []
    text = wl.read_text(encoding="utf-8")
    # Match tickers: plain uppercase (SPY), hyphenated crypto (BTC-USD),
    # or alphanumeric yfinance IDs (SUI20947-USD)
    tickers = re.findall(r"^\|\s*([A-Z][A-Z0-9]{1,9}(?:-[A-Z]{2,4})?)\s*\|", text, re.MULTILINE)
    EXCLUDE = {"ETF", "DXY", "VIX"}
    seen, result = set(), []
    for t in tickers:
        if t not in seen and t not in EXCLUDE:
            seen.add(t)
            result.append(t)
    return result


# ── computation ───────────────────────────────────────────────────────────────

def compute_indicators(df: pd.DataFrame) -> pd.DataFrame:
    """Compute all TA indicators for a full OHLCV DataFrame.

    Input columns (case-insensitive): open, high, low, close, volume.
    Returns a new DataFrame with one row per date and all indicator columns.
    NaN where insufficient history exists.
    """
    ta = _ta()

    df = df.copy()
    df.columns = [c.lower() for c in df.columns]
    df = df.sort_index()

    close = df["close"]
    high  = df["high"]
    low   = df["low"]

    # ── Moving Averages ──────────────────────────────────────────────────────
    sma_20  = ta.sma(close, length=20)
    sma_50  = ta.sma(close, length=50)
    sma_200 = ta.sma(close, length=200)
    ema_12  = ta.ema(close, length=12)
    ema_26  = ta.ema(close, length=26)
    ema_50  = ta.ema(close, length=50)

    pct_vs_sma20  = ((close - sma_20)  / sma_20  * 100).round(4)
    pct_vs_sma50  = ((close - sma_50)  / sma_50  * 100).round(4)
    pct_vs_sma200 = ((close - sma_200) / sma_200 * 100).round(4)

    # ── Trend Strength (ADX / DMI) ───────────────────────────────────────────
    adx_df    = ta.adx(high, low, close, length=14)
    adx_14    = adx_df.get("ADX_14")    if adx_df is not None else None
    dmi_plus  = adx_df.get("DMP_14")    if adx_df is not None else None
    dmi_minus = adx_df.get("DMN_14")    if adx_df is not None else None

    # ── Momentum ─────────────────────────────────────────────────────────────
    rsi_7  = ta.rsi(close, length=7)
    rsi_14 = ta.rsi(close, length=14)
    rsi_21 = ta.rsi(close, length=21)

    macd_df    = ta.macd(close, fast=12, slow=26, signal=9)
    macd       = macd_df.get("MACD_12_26_9")   if macd_df is not None else None
    macd_sig   = macd_df.get("MACDs_12_26_9")  if macd_df is not None else None
    macd_hist  = macd_df.get("MACDh_12_26_9")  if macd_df is not None else None

    roc_5  = ta.roc(close, length=5)
    roc_10 = ta.roc(close, length=10)
    roc_21 = ta.roc(close, length=21)

    # ── Volatility ───────────────────────────────────────────────────────────
    atr_14  = ta.atr(high, low, close, length=14)
    atr_pct = (atr_14 / close * 100).round(4)

    bb_df       = ta.bbands(close, length=20, std=2)
    # Column names vary by pandas_ta version: try both "BBU_20_2.0" and "BBU_20_2.0_2.0"
    if bb_df is not None:
        _bbu_key  = next((c for c in bb_df.columns if c.startswith("BBU_")), None)
        _bbm_key  = next((c for c in bb_df.columns if c.startswith("BBM_")), None)
        _bbl_key  = next((c for c in bb_df.columns if c.startswith("BBL_")), None)
        _bbp_key  = next((c for c in bb_df.columns if c.startswith("BBP_")), None)
        _bbb_key  = next((c for c in bb_df.columns if c.startswith("BBB_")), None)
        bb_upper    = bb_df[_bbu_key]  if _bbu_key  else None
        bb_middle   = bb_df[_bbm_key]  if _bbm_key  else None
        bb_lower    = bb_df[_bbl_key]  if _bbl_key  else None
        bb_pct_b    = bb_df[_bbp_key]  if _bbp_key  else None
        bb_bandwidth = bb_df[_bbb_key] if _bbb_key  else None
    else:
        bb_upper = bb_middle = bb_lower = bb_pct_b = bb_bandwidth = None

    # 21-day realized volatility: annualized std of log returns (%)
    log_ret  = np.log(close / close.shift(1))
    hist_vol = log_ret.rolling(21).std() * np.sqrt(252) * 100

    # ── Mean Reversion / Oscillators ─────────────────────────────────────────
    stoch_df = ta.stoch(high, low, close, k=14, d=3, smooth_k=3)
    stoch_k  = stoch_df.get("STOCHk_14_3_3") if stoch_df is not None else None
    stoch_d  = stoch_df.get("STOCHd_14_3_3") if stoch_df is not None else None

    # Z-scores: (close - ma) / rolling_std
    zscore_50  = ((close - sma_50)  / close.rolling(50).std()).round(4)
    zscore_200 = ((close - sma_200) / close.rolling(200).std()).round(4)

    # ── Assemble ─────────────────────────────────────────────────────────────
    out = pd.DataFrame({
        "sma_20":       sma_20,
        "sma_50":       sma_50,
        "sma_200":      sma_200,
        "ema_12":       ema_12,
        "ema_26":       ema_26,
        "ema_50":       ema_50,
        "pct_vs_sma20":  pct_vs_sma20,
        "pct_vs_sma50":  pct_vs_sma50,
        "pct_vs_sma200": pct_vs_sma200,
        "adx_14":       adx_14,
        "dmi_plus":     dmi_plus,
        "dmi_minus":    dmi_minus,
        "rsi_7":        rsi_7,
        "rsi_14":       rsi_14,
        "rsi_21":       rsi_21,
        "macd":         macd,
        "macd_signal":  macd_sig,
        "macd_hist":    macd_hist,
        "roc_5":        roc_5,
        "roc_10":       roc_10,
        "roc_21":       roc_21,
        "atr_14":       atr_14,
        "atr_pct":      atr_pct,
        "bb_upper":     bb_upper,
        "bb_middle":    bb_middle,
        "bb_lower":     bb_lower,
        "bb_pct_b":     bb_pct_b,
        "bb_bandwidth": bb_bandwidth,
        "hist_vol_21":  hist_vol,
        "stoch_k":      stoch_k,
        "stoch_d":      stoch_d,
        "zscore_50":    zscore_50,
        "zscore_200":   zscore_200,
    }, index=df.index)

    return out


# ── Supabase upsert ───────────────────────────────────────────────────────────

def get_supabase_client():
    """Return an authenticated supabase-py client using config/supabase.env."""
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
        print("  ⚠️  SUPABASE_URL / SUPABASE_SERVICE_KEY not set — skipping upsert")
        return None
    return create_client(url, key)


def upsert_to_supabase(sb, ticker: str, ind_df: pd.DataFrame) -> int:
    """Upsert computed indicator rows for one ticker. Returns row count."""
    rows = []
    for date_idx, row in ind_df.iterrows():
        r = {"date": str(date_idx)[:10], "ticker": ticker}
        for col in ind_df.columns:
            r[col] = safe_float(row[col])
        rows.append(r)

    if not rows:
        return 0

    CHUNK = 500
    for i in range(0, len(rows), CHUNK):
        sb.table("price_technicals").upsert(rows[i:i + CHUNK]).execute()
    return len(rows)


# ── main ─────────────────────────────────────────────────────────────────────

def main():
    parser = argparse.ArgumentParser(
        description="Compute multi-timeframe TA indicators and upsert to price_technicals"
    )
    parser.add_argument("--ticker", default=None,
                        help="Process a single ticker instead of the full watchlist")
    parser.add_argument("--days", type=int, default=365,
                        help="Compute only the last N rows per ticker (default: 365). "
                             "Ignored if --all is set.")
    parser.add_argument("--all", action="store_true",
                        help="Compute full history for all tickers (slow, use for backfill)")
    parser.add_argument("--supabase", action="store_true",
                        help="Upsert results to Supabase price_technicals table")
    parser.add_argument("--dry-run", action="store_true",
                        help="Compute but do not write to Supabase")
    args = parser.parse_args()

    print("╔══════════════════════════════════════════════╗")
    print("║  compute-technicals.py — TA Indicator Engine ║")
    print("╚══════════════════════════════════════════════╝")

    # ── ticker list ──────────────────────────────────────────────────────────
    if args.ticker:
        tickers = [args.ticker.upper()]
    else:
        tickers = parse_tickers_from_watchlist()
        print(f"  Tickers  : {len(tickers)} from config/watchlist.md")

    window = "full history" if args.all else f"last {args.days} rows"
    print(f"  Window   : {window}")
    print(f"  Supabase : {'yes' if args.supabase and not args.dry_run else 'dry-run' if args.dry_run else 'no'}")
    print()

    # ── Supabase client ──────────────────────────────────────────────────────
    sb = None
    if args.supabase and not args.dry_run:
        sb = get_supabase_client()

    # ── process each ticker ──────────────────────────────────────────────────
    total_rows = 0
    skipped = 0
    t0 = time.time()

    for ticker in tickers:
        csv_path = CACHE_DIR / f"{ticker}.csv"
        if not csv_path.exists():
            print(f"    ⚠️  {ticker:6s}  no cache — run preload-history.py first")
            skipped += 1
            continue

        try:
            df = pd.read_csv(csv_path, parse_dates=["Date"], index_col="Date")
            df = df.sort_index()
        except Exception as e:
            print(f"    ❌ {ticker:6s}  read error: {e}")
            skipped += 1
            continue

        if len(df) < MIN_BARS:
            print(f"    ⚠️  {ticker:6s}  only {len(df)} bars — need {MIN_BARS}+ to compute")
            skipped += 1
            continue

        # Compute indicators over full history (need all bars for rolling calcs)
        # then slice to the output window
        ind_df = compute_indicators(df)

        if not args.all:
            ind_df = ind_df.tail(args.days)

        # Drop rows where all indicator columns are NaN (leading NaN window)
        ind_df = ind_df.dropna(how="all")

        rows_computed = len(ind_df)
        first = ind_df.index.min().strftime("%Y-%m-%d") if not ind_df.empty else "—"
        last  = ind_df.index.max().strftime("%Y-%m-%d") if not ind_df.empty else "—"

        sb_note = ""
        if sb is not None:
            upserted = upsert_to_supabase(sb, ticker, ind_df)
            sb_note  = f"  ↑Supabase {upserted}r"
            total_rows += upserted
        else:
            total_rows += rows_computed

        print(f"    ✅ {ticker:6s}  {rows_computed:>4d} rows  {first} → {last}{sb_note}")

    elapsed = time.time() - t0
    print()
    print(f"  Processed {len(tickers) - skipped}/{len(tickers)} tickers in {elapsed:.1f}s")
    if sb is not None:
        print(f"  Upserted  {total_rows} rows to Supabase price_technicals")
    print("  Done.")


if __name__ == "__main__":
    main()
