#!/usr/bin/env python3
"""
ingest_treasury_curve.py — Treasury yields → macro_series_observations.

1) US Treasury XML (when the feed returns entries — often empty from data centers).
2) Yahoo Finance ^IRX/^FVX/^TNX/^TYX fallback (reliable daily; labeled treasury_market).

Usage:
  python3 scripts/ingest_treasury_curve.py --dry-run
  python3 scripts/ingest_treasury_curve.py --supabase
  python3 scripts/ingest_treasury_curve.py --supabase --backfill
  python3 scripts/ingest_treasury_curve.py --supabase --backfill --xml-months 420   # rare: full XML from home/VPN
"""

from __future__ import annotations

import argparse
import sys
from datetime import date, datetime, timedelta
from pathlib import Path

import pandas as pd
import requests
import yfinance as yf

ROOT = Path(__file__).resolve().parent.parent
if str(ROOT / "scripts") not in sys.path:
    sys.path.insert(0, str(ROOT / "scripts"))

from lib.macro_ingest import (  # noqa: E402
    connect_supabase,
    latest_obs_date_for_source,
    load_config_env,
    upsert_observations,
)
from lib.treasury_xml import TREASURY_MATURITIES, TREASURY_XML_URL, parse_treasury_month_xml  # noqa: E402

SOURCE_XML = "us_treasury"
SOURCE_MARKET = "treasury_market"
OVERLAP_DAYS = 5

YAHOO_TREASURY = {
    "3M": "^IRX",
    "5Y": "^FVX",
    "10Y": "^TNX",
    "30Y": "^TYX",
}


def _log(msg: str, *, file=sys.stdout) -> None:
    print(msg, file=file, flush=True)


def add_months_first(d: date, delta: int) -> date:
    y, m = d.year, d.month + delta
    while m > 12:
        m -= 12
        y += 1
    while m < 1:
        m += 12
        y -= 1
    return date(y, m, 1)


def fetch_month(yyyymm: str) -> str:
    url = TREASURY_XML_URL.format(yyyymm=yyyymm)
    r = requests.get(url, timeout=(10, 45))
    r.raise_for_status()
    return r.text


def iter_months_backward(start_month: date, end_month: date):
    y, m = start_month.year, start_month.month
    ey, em = end_month.year, end_month.month
    while (y, m) >= (ey, em):
        yield f"{y:04d}{m:02d}"
        if m == 1:
            y -= 1
            m = 12
        else:
            m -= 1


def curves_to_rows(curves: list[tuple[str, dict[str, float]]], source: str, meta: dict) -> list[dict]:
    rows: list[dict] = []
    for obs_date, yields in curves:
        for _xml_key, label in TREASURY_MATURITIES:
            v = yields.get(label)
            if v is None:
                continue
            rows.append(
                {
                    "source": source,
                    "series_id": f"YC/{label}",
                    "obs_date": obs_date,
                    "value": float(v),
                    "unit": "percent",
                    "meta": meta.copy(),
                }
            )
    return rows


def yahoo_treasury_rows(period: str) -> list[dict]:
    """Daily closes for key tenors via Yahoo (percent units)."""
    syms = list(YAHOO_TREASURY.values())
    try:
        # threads=False: avoids intermittent hangs in CI / Actions with threads=True
        raw = yf.download(syms, period=period, progress=False, threads=False)["Close"]
    except Exception as e:
        _log(f"  ⚠️  yfinance treasury: {e}", file=sys.stderr)
        return []
    if raw is None or raw.empty:
        return []

    rows: list[dict] = []
    for ts in raw.index:
        obs = pd.Timestamp(ts).strftime("%Y-%m-%d")
        for label, sym in YAHOO_TREASURY.items():
            try:
                if isinstance(raw.columns, pd.MultiIndex):
                    v = raw.loc[ts, sym]
                elif sym in raw.columns:
                    v = raw.loc[ts, sym]
                elif len(syms) == 1:
                    v = float(raw.loc[ts])
                else:
                    continue
            except Exception:
                continue
            if v is None or (isinstance(v, float) and pd.isna(v)):
                continue
            try:
                fv = float(v)
            except (TypeError, ValueError):
                continue
            rows.append(
                {
                    "source": SOURCE_MARKET,
                    "series_id": f"YC/{label}",
                    "obs_date": obs,
                    "value": round(fv, 4),
                    "unit": "percent",
                    "meta": {"via": "yfinance"},
                }
            )
    return rows


def main() -> int:
    p = argparse.ArgumentParser(description="Ingest Treasury yields into Supabase")
    p.add_argument("--dry-run", action="store_true")
    p.add_argument("--supabase", action="store_true")
    p.add_argument(
        "--backfill",
        action="store_true",
        help="Yahoo period=max for deep history; skips Treasury XML month crawl by default (slow, often 0 rows from cloud)",
    )
    p.add_argument(
        "--xml-months",
        type=int,
        default=None,
        metavar="N",
        help="Treasury.gov XML months to fetch backward from this month (default: 4 without --backfill, 0 with --backfill). "
        "Use e.g. 420 only when the feed returns data (often not from GitHub Actions).",
    )
    args = p.parse_args()

    load_config_env()

    today = date.today()
    sb = connect_supabase() if args.supabase else None
    if args.supabase and not sb:
        _log("Supabase not configured", file=sys.stderr)
        return 1

    if args.xml_months is not None:
        month_span = max(0, args.xml_months)
    elif args.backfill:
        month_span = 0
    else:
        month_span = 4
    yahoo_period = "max" if args.backfill else "3mo"
    start_anchor = today.replace(day=1)
    if month_span == 0:
        months = []
    else:
        end_anchor = add_months_first(start_anchor, -(month_span - 1))
        months = list(iter_months_backward(start_anchor, end_anchor))
    total_m = len(months)
    if month_span == 0:
        _log(
            f"ingest_treasury_curve: backfill={args.backfill} — Treasury XML: skipped; "
            f"Yahoo period={yahoo_period} (add --xml-months N for official XML crawl)"
        )
    else:
        _log(
            f"ingest_treasury_curve: backfill={args.backfill} "
            f"— {total_m} Treasury XML months ({end_anchor.isoformat()} → {start_anchor.isoformat()}), "
            f"Yahoo period={yahoo_period}"
        )

    all_curves: list[tuple[str, dict[str, float]]] = []
    seen_dates: set[str] = set()
    for i, yyyymm in enumerate(months, 1):
        _log(f"  XML [{i}/{total_m}] {yyyymm} …")
        try:
            xml = fetch_month(yyyymm)
        except Exception as e:
            _log(f"  ⚠️  XML {yyyymm}: {e}")
            continue
        parsed = parse_treasury_month_xml(xml)
        _log(f"  XML [{i}/{total_m}] {yyyymm}: {len(parsed)} curve dates")
        for d, yd in parsed:
            if d not in seen_dates:
                seen_dates.add(d)
                all_curves.append((d, yd))

    last_xml: str | None = None
    if args.supabase and sb and not args.backfill:
        last_xml = latest_obs_date_for_source(sb, SOURCE_XML)
    if last_xml:
        cutoff = (datetime.strptime(last_xml, "%Y-%m-%d").date() - timedelta(days=OVERLAP_DAYS)).isoformat()
        all_curves = [(d, y) for d, y in all_curves if d >= cutoff]

    rows_xml = curves_to_rows(
        all_curves,
        SOURCE_XML,
        {"curve": "daily_treasury_xml", "official": True},
    )

    _log(f"  Yahoo Finance: downloading {list(YAHOO_TREASURY.values())} period={yahoo_period} …")
    rows_yf = yahoo_treasury_rows(yahoo_period)
    _log(f"  Yahoo Finance: parsed {len(rows_yf)} row fragments")
    if not args.backfill and sb and rows_yf:
        last_m = latest_obs_date_for_source(sb, SOURCE_MARKET)
        if last_m:
            cut = (datetime.strptime(last_m, "%Y-%m-%d").date() - timedelta(days=OVERLAP_DAYS)).isoformat()
            rows_yf = [r for r in rows_yf if r["obs_date"] >= cut]

    rows = rows_xml + rows_yf
    rows.sort(key=lambda r: (r["source"], r["series_id"], r["obs_date"]))

    _log(f"  XML rows: {len(rows_xml)}  Yahoo rows: {len(rows_yf)}  total: {len(rows)}")

    if args.dry_run:
        if rows:
            ds = [r["obs_date"] for r in rows]
            _log(f"  date range: {min(ds)} .. {max(ds)}")
        return 0

    if not args.supabase or not sb:
        _log("Use --supabase to upsert (or --dry-run)", file=sys.stderr)
        return 1

    _log(f"  Supabase upsert: {len(rows)} rows …")
    n = upsert_observations(sb, rows)
    _log(f"Upserted {n} treasury rows")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
