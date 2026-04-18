#!/usr/bin/env python3
"""
fetch-macro.py — Systematic macro data snapshot (yield curve, volatility, commodities, crypto, FX)
Uses:
  - US Treasury public XML API for the full yield curve (1M–30Y, no auth required)
  - yfinance for VIX, SKEW, crude oil, gold, natural gas, BTC, ETH, USD/CAD, EUR/USD,
    and credit proxy ETFs (HYG, LQD, JNK, TLT, BIL)

Writes macro.json + macro-summary.md to the daily data folder.

Usage:
    python3 scripts/fetch-macro.py                  # today
    python3 scripts/fetch-macro.py 2026-04-06       # specific date
"""

import argparse
import json
import sys
import time
from datetime import datetime, date
from pathlib import Path
from xml.etree import ElementTree

import numpy as np
import pandas as pd
import requests
import yfinance as yf

ROOT = Path(__file__).parent.parent

# Treasury XML API — returns daily yield curve data
TREASURY_XML_URL = (
    "https://home.treasury.gov/resource-center/data-chart-center/"
    "interest-rates/pages/xml?data=daily_treasury_yield_curve&field_tdr_date_value={yyyymm}"
)

# Maturities we care about in order
TREASURY_MATURITIES = [
    ("1_MONTH",  "1M"),
    ("2_MONTH",  "2M"),
    ("3_MONTH",  "3M"),
    ("6_MONTH",  "6M"),
    ("1_YEAR",   "1Y"),
    ("2_YEAR",   "2Y"),
    ("3_YEAR",   "3Y"),
    ("5_YEAR",   "5Y"),
    ("7_YEAR",   "7Y"),
    ("10_YEAR",  "10Y"),
    ("20_YEAR",  "20Y"),
    ("30_YEAR",  "30Y"),
]

# yfinance symbols for macro series
MACRO_SYMBOLS = {
    "vix":      "^VIX",
    "skew":     "^SKEW",
    "crude":    "CL=F",     # WTI crude futures
    "brent":    "BZ=F",     # Brent crude futures
    "gold":     "GC=F",     # Gold futures
    "silver":   "SI=F",     # Silver futures
    "natgas":   "NG=F",     # Natural gas futures
    "copper":   "HG=F",     # Copper futures
    "btc":      "BTC-USD",
    "eth":      "ETH-USD",
    "usdcad":   "USDCAD=X",
    "eurusd":   "EURUSD=X",
    "usdjpy":   "USDJPY=X",
    "gbpusd":   "GBPUSD=X",
    "dxy":      "DX-Y.NYB",  # Dollar Index
    # Credit/rate proxies
    "hyg":      "HYG",
    "lqd":      "LQD",
    "jnk":      "JNK",
    "tlt":      "TLT",
    "bil":      "BIL",
    "spy":      "SPY",     # benchmark
}


# ── yield curve ──────────────────────────────────────────────────────────────

def fetch_treasury_yield_curve_yfinance() -> dict:
    """
    Fallback: fetch key US Treasury yield points from Yahoo Finance.
    Covers 3M (^IRX), 5Y (^FVX), 10Y (^TNX), 30Y (^TYX).
    Yahoo Finance returns these values already in % units (e.g. 4.5 = 4.5%).
    """
    yield_symbols = {
        "3M": "^IRX",
        "5Y": "^FVX",
        "10Y": "^TNX",
        "30Y": "^TYX",
    }
    try:
        syms = list(yield_symbols.values())
        raw = yf.download(syms, period="5d", progress=False, threads=True)["Close"]
        yields = {}
        as_of = None
        for label, sym in yield_symbols.items():
            try:
                if isinstance(raw.columns, pd.MultiIndex):
                    series = raw[sym].dropna()
                elif sym in raw.columns:
                    series = raw[sym].dropna()
                else:
                    series = raw.dropna() if len(syms) == 1 else None

                if series is not None and len(series) > 0:
                    yields[label] = round(float(series.iloc[-1]), 3)
                    if as_of is None:
                        as_of = series.index[-1].strftime("%Y-%m-%d")
            except Exception:
                pass

        if yields:
            return {
                "source": "Yahoo Finance (^IRX/^FVX/^TNX/^TYX)",
                "curve_date": as_of or "unknown",
                "fetched_month": None,
                "partial": True,
                "yields": yields,
            }
    except Exception as e:
        print(f"  ⚠️  yfinance yield curve fallback failed: {e}")
    return {"source": "yfinance fallback", "error": "no_data", "yields": {}}


def fetch_treasury_yield_curve(target_date_str: str) -> dict:
    """
    Fetch the latest yield curve from the US Treasury XML API.
    Tries the current month first; if no data, falls back to prior months (up to 6).
    If the XML API fails entirely, falls back to Yahoo Finance yield tickers.
    Returns dict with maturity label → yield (%), plus metadata.
    """
    dt = datetime.strptime(target_date_str, "%Y-%m-%d")

    # Build list of months to try (most recent first, up to 6 months back)
    months_to_try = []
    m = dt
    for _ in range(6):
        months_to_try.append(m.strftime("%Y%m"))
        # Move one month back
        if m.month == 1:
            m = m.replace(year=m.year - 1, month=12)
        else:
            m = m.replace(month=m.month - 1)

    for yyyymm in months_to_try:
        url = TREASURY_XML_URL.format(yyyymm=yyyymm)
        try:
            resp = requests.get(url, timeout=15)
            resp.raise_for_status()
        except Exception as e:
            print(f"  ⚠️  Treasury XML fetch failed ({yyyymm}): {e}")
            continue

        try:
            root = ElementTree.fromstring(resp.text)
        except ElementTree.ParseError as e:
            print(f"  ⚠️  Treasury XML parse error: {e}")
            continue

        # Namespace prefix used in the feed
        ns = {"m": "http://schemas.microsoft.com/ado/2007/08/dataservices/metadata",
              "d": "http://schemas.microsoft.com/ado/2007/08/dataservices",
              "a": "http://www.w3.org/2005/Atom"}

        # Find all entry elements
        entries = root.findall(".//a:entry", ns)
        if not entries:
            # Try without namespace
            entries = root.findall(".//{http://www.w3.org/2005/Atom}entry")

        if not entries:
            continue  # no data for this month — try previous

        latest_entry = entries[-1]

        # Extract the date from the entry content
        props = latest_entry.find(".//{http://schemas.microsoft.com/ado/2007/08/dataservices/metadata}properties")
        if props is None:
            continue

        def get_prop(name):
            el = props.find(f"{{http://schemas.microsoft.com/ado/2007/08/dataservices}}{name}")
            return el.text if el is not None else None

        raw_date = get_prop("NEW_DATE") or ""
        try:
            curve_date = raw_date[:10]
        except Exception:
            curve_date = yyyymm

        yields = {}
        for xml_key, label in TREASURY_MATURITIES:
            val = get_prop(f"BC_{xml_key}")
            if val:
                try:
                    yields[label] = round(float(val), 3)
                except ValueError:
                    pass

        if yields:
            # Verify that the anchor maturities needed for spread calculations are present.
            # If the XML schema changed, partially populated yields would silently break
            # compute_spreads(). Warn and try the next month instead.
            required_keys = {"2Y", "10Y"}
            missing_keys = required_keys - yields.keys()
            if missing_keys:
                print(f"  ⚠️  Treasury XML ({yyyymm}): yields missing required keys {missing_keys} — trying next month")
                continue
            return {
                "source": "US Treasury XML API",
                "curve_date": curve_date,
                "fetched_month": yyyymm,
                "yields": yields,
            }

    # All XML attempts failed — fall back to yfinance
    print("  ℹ️  Treasury XML returned no data for any recent month. Using yfinance yield fallback...")
    return fetch_treasury_yield_curve_yfinance()


def compute_spreads(yields: dict) -> dict:
    """Compute standard yield curve spreads from the yields dict."""
    spreads = {}
    pairs = [
        ("2s10s",  "2Y", "10Y"),
        ("3m10y",  "3M", "10Y"),
        ("5s30s",  "5Y", "30Y"),
        ("2s30s",  "2Y", "30Y"),
    ]
    for label, short, long in pairs:
        s = yields.get(short)
        l = yields.get(long)
        if s is not None and l is not None:
            spreads[label] = round(l - s, 3)
    return spreads


def inversion_flags(spreads: dict) -> list[str]:
    flags = []
    if spreads.get("2s10s") is not None and spreads["2s10s"] < 0:
        flags.append(f"2s10s INVERTED ({spreads['2s10s']:+.2f}bps)")
    if spreads.get("3m10y") is not None and spreads["3m10y"] < 0:
        flags.append(f"3m10Y INVERTED ({spreads['3m10y']:+.2f}bps)")
    return flags


# ── yfinance macro series ─────────────────────────────────────────────────────

def safe_float(val, decimals: int = 2):
    try:
        f = float(val)
        if pd.isna(f) or not np.isfinite(f):
            return None
        return round(f, decimals)
    except (TypeError, ValueError):
        return None


def fetch_macro_series() -> dict:
    """Fetch latest price + 1d change for all MACRO_SYMBOLS."""
    symbols = list(MACRO_SYMBOLS.values())
    # Download last 5 trading days to ensure we get today's close + prior
    try:
        raw = yf.download(symbols, period="5d", progress=False, threads=True)["Close"]
    except Exception as e:
        print(f"  ⚠️  yfinance macro download failed: {e}")
        return {}

    results = {}
    for key, sym in MACRO_SYMBOLS.items():
        try:
            if isinstance(raw.columns, pd.Index) and sym in raw.columns:
                series = raw[sym].dropna()
            elif not isinstance(raw.columns, pd.MultiIndex):
                series = raw.dropna()
            else:
                continue

            if len(series) < 1:
                continue

            price = safe_float(series.iloc[-1])
            prev = safe_float(series.iloc[-2]) if len(series) >= 2 else None
            pct_1d = round((price - prev) / prev * 100, 2) if price and prev and prev > 0 else None

            results[key] = {
                "symbol": sym,
                "price": price,
                "pct_1d": pct_1d,
                "as_of": series.index[-1].strftime("%Y-%m-%d") if hasattr(series.index[-1], "strftime") else str(series.index[-1]),
            }
        except Exception as e:
            results[key] = {"symbol": sym, "error": str(e)}

    return results


# ── markdown output ───────────────────────────────────────────────────────────

def write_summary_md(yield_data: dict, spreads: dict, inversions: list,
                     macro_series: dict, output_path: Path, fetched_at: str):
    """Write human-readable macro-summary.md."""
    yields = yield_data.get("yields", {})
    curve_date = yield_data.get("curve_date", "unknown")
    curve_error = yield_data.get("error")

    lines = [
        f"# Macro Data Snapshot — {fetched_at}",
        "",
        "> **Data sources**: US Treasury XML API (yield curve) + Yahoo Finance (volatility, commodities, crypto, FX).",
        "> **Freshness**: Yield curve = prior business day close. Market series = ~15min delayed.",
        "",
        "---",
        "",
    ]

    # ── Yield Curve ──
    lines += [
        "## Yield Curve (US Treasuries)",
        f"> Source: US Treasury (as of {curve_date})",
        "",
    ]
    if curve_error:
        lines.append(f"> ⚠️ **Could not fetch yield curve**: {curve_error}")
    else:
        lines += [
            "| Maturity | Yield |",
            "|----------|-------|",
        ]
        for _, label in TREASURY_MATURITIES:
            y = yields.get(label)
            if y is not None:
                lines.append(f"| {label} | {y:.3f}% |")

        lines += [""]

        if spreads:
            lines += [
                "### Key Spreads",
                "",
                "| Spread | Value | Signal |",
                "|--------|-------|--------|",
            ]
            for k, v in spreads.items():
                signal = "⚠️ INVERTED" if v < 0 else ("🟡 Flat (<25bps)" if v < 0.25 else "✅ Normal")
                lines.append(f"| {k} | {v:+.3f}% | {signal} |")
            lines += [""]

        if inversions:
            lines += [
                "### ⚠️ Active Inversions",
                "",
            ]
            for inv in inversions:
                lines.append(f"- {inv}")
            lines += [""]

    lines += ["---", ""]

    # ── Volatility ──
    vix = macro_series.get("vix", {})
    skew = macro_series.get("skew", {})
    lines += [
        "## Volatility",
        "",
        "| Index | Level | 1D Change |",
        "|-------|-------|-----------|",
    ]
    for label, key in [("VIX", "vix"), ("SKEW", "skew")]:
        s = macro_series.get(key, {})
        p = s.get("price", "–")
        c = f"{s['pct_1d']:+.2f}%" if s.get("pct_1d") is not None else "–"
        lines.append(f"| {label} | {p} | {c} |")

    # VIX regime commentary
    vix_level = vix.get("price")
    if vix_level:
        if vix_level < 15:
            vix_regime = "🟢 Complacency (<15)"
        elif vix_level < 20:
            vix_regime = "🟡 Normal (15–20)"
        elif vix_level < 30:
            vix_regime = "🟠 Elevated (20–30)"
        else:
            vix_regime = "🔴 Stress (>30)"
        lines.append(f"\n> **VIX regime**: {vix_regime}")
    lines += ["", "---", ""]

    # ── Commodities ──
    lines += [
        "## Commodities",
        "",
        "| Commodity | Price | 1D Change |",
        "|-----------|-------|-----------|",
    ]
    commodity_keys = [("WTI Crude", "crude"), ("Brent Crude", "brent"), ("Gold", "gold"),
                      ("Silver", "silver"), ("Natural Gas", "natgas"), ("Copper", "copper")]
    for label, key in commodity_keys:
        s = macro_series.get(key, {})
        p = s.get("price", "–")
        c = f"{s['pct_1d']:+.2f}%" if s.get("pct_1d") is not None else "–"
        lines.append(f"| {label} | {p} | {c} |")
    lines += ["", "---", ""]

    # ── Crypto ──
    lines += [
        "## Crypto",
        "",
        "| Asset | Price | 1D Change |",
        "|-------|-------|-----------|",
    ]
    for label, key in [("Bitcoin (BTC)", "btc"), ("Ethereum (ETH)", "eth")]:
        s = macro_series.get(key, {})
        p = s.get("price", "–")
        c = f"{s['pct_1d']:+.2f}%" if s.get("pct_1d") is not None else "–"
        lines.append(f"| {label} | {p} | {c} |")
    lines += ["", "---", ""]

    # ── FX ──
    lines += [
        "## FX Rates",
        "",
        "| Pair | Rate | 1D Change |",
        "|------|------|-----------|",
    ]
    fx_keys = [("USD/CAD", "usdcad"), ("EUR/USD", "eurusd"), ("USD/JPY", "usdjpy"),
               ("GBP/USD", "gbpusd"), ("DXY (Dollar Index)", "dxy")]
    for label, key in fx_keys:
        s = macro_series.get(key, {})
        p = s.get("price", "–")
        c = f"{s['pct_1d']:+.2f}%" if s.get("pct_1d") is not None else "–"
        lines.append(f"| {label} | {p} | {c} |")
    lines += ["", "---", ""]

    # ── Credit / Rates ──
    lines += [
        "## Credit & Rate Proxies (ETFs)",
        "",
        "| ETF | Price | 1D Change |",
        "|-----|-------|-----------|",
    ]
    credit_keys = [("HYG (High Yield)", "hyg"), ("LQD (Investment Grade)", "lqd"),
                   ("JNK (High Yield)", "jnk"), ("TLT (20Y Treasury)", "tlt"),
                   ("BIL (T-Bills)", "bil"), ("SPY (S&P 500)", "spy")]
    for label, key in credit_keys:
        s = macro_series.get(key, {})
        p = s.get("price", "–")
        c = f"{s['pct_1d']:+.2f}%" if s.get("pct_1d") is not None else "–"
        lines.append(f"| {label} | {p} | {c} |")
    lines += [""]

    output_path.write_text("\n".join(lines) + "\n", encoding="utf-8")


# ── main ─────────────────────────────────────────────────────────────────────

def main():
    parser = argparse.ArgumentParser(
        description="fetch-macro.py — Systematic macro data snapshot (yield curve, VIX, FX, commodities, crypto)",
        epilog="Uses US Treasury public XML API for yield curve; yfinance for everything else."
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

    print(f"fetch-macro.py — {target_date}")

    print("  Fetching US Treasury yield curve...")
    yield_data = fetch_treasury_yield_curve(target_date)
    yields = yield_data.get("yields", {})
    spreads = compute_spreads(yields)
    inversions = inversion_flags(spreads)

    if yields:
        print(f"  ✅ Yield curve: {len(yields)} maturities as of {yield_data.get('curve_date','?')}")
    else:
        print(f"  ⚠️  Yield curve unavailable: {yield_data.get('error','unknown error')}")

    print("  Fetching yfinance macro series (VIX, commodities, FX, crypto)...")
    macro_series = fetch_macro_series()
    ok = sum(1 for v in macro_series.values() if "error" not in v)
    print(f"  ✅ {ok}/{len(MACRO_SYMBOLS)} macro series fetched")

    output = {
        "date": target_date,
        "fetched_at": fetched_at,
        "yield_curve": yield_data,
        "spreads": spreads,
        "inversions": inversions,
        "series": macro_series,
    }

    macro_json = out_dir / "macro.json"
    macro_json.write_text(json.dumps(output, indent=2, default=str), encoding="utf-8")
    print(f"  ✅ Wrote {macro_json}")

    macro_md = out_dir / "macro-summary.md"
    write_summary_md(yield_data, spreads, inversions, macro_series, macro_md, fetched_at)
    print(f"  ✅ Wrote {macro_md}")

    if inversions:
        print(f"  ⚠️  Yield curve inversion signals: {', '.join(inversions)}")

    print("  Done.")


if __name__ == "__main__":
    main()
