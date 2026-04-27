#!/usr/bin/env python3
"""
Fill position_events.price from price_history.open when execution ran before opens existed.

Typical flow: pre-market run_db_first → execute_at_open records events with price=null →
after the session (or after price sync), run this script for that date.

Usage:
  python3 scripts/backfill_execution_prices.py [--date YYYY-MM-DD]
Environment: SUPABASE_URL, SUPABASE_SERVICE_KEY
"""

from __future__ import annotations

import argparse
import os
import sys
from datetime import date as dt_date
from pathlib import Path
from typing import Any, Dict, List, Optional

try:
    from supabase import create_client  # type: ignore

    _HAS_SB = True
except ImportError:
    _HAS_SB = False

try:
    from dotenv import load_dotenv  # type: ignore

    load_dotenv(Path(__file__).parent.parent / "config" / "supabase.env")
    load_dotenv()
except ImportError:
    pass


def _sb():
    if not _HAS_SB:
        raise RuntimeError("pip install supabase")
    url = os.environ.get("SUPABASE_URL")
    key = os.environ.get("SUPABASE_SERVICE_KEY")
    if not url or not key:
        raise RuntimeError("SUPABASE_URL and SUPABASE_SERVICE_KEY required")
    return create_client(url, key)


def _fetch_open(sb, ticker: str, d: str) -> Optional[float]:
    res = (
        sb.table("price_history")
        .select("open")
        .eq("ticker", ticker)
        .eq("date", d)
        .limit(1)
        .execute()
    )
    rows = getattr(res, "data", None) or []
    if not rows:
        return None
    o = rows[0].get("open")
    return float(o) if o is not None else None


def main() -> int:
    ap = argparse.ArgumentParser(description="Backfill position_events.price from price_history.open.")
    ap.add_argument("--date", default=dt_date.today().isoformat(), help="YYYY-MM-DD")
    args = ap.parse_args()
    d = args.date

    sb = _sb()
    res = (
        sb.table("position_events")
        .select("date,ticker,event,price,weight_pct,reason,thesis_id")
        .eq("date", d)
        .is_("price", "null")
        .execute()
    )
    rows: List[Dict[str, Any]] = getattr(res, "data", None) or []
    if not rows:
        print(f"No null-price position_events for {d}.")
        return 0

    updated = 0
    for row in rows:
        ticker = row.get("ticker")
        if not ticker:
            continue
        px = _fetch_open(sb, str(ticker), d)
        if px is None:
            print(f"   skip {ticker}: no price_history.open for {d}")
            continue
        up = {
            "date": d,
            "ticker": str(ticker),
            "event": row.get("event"),
            "weight_pct": row.get("weight_pct"),
            "price": px,
            "reason": row.get("reason"),
            "thesis_id": row.get("thesis_id"),
        }
        sb.table("position_events").upsert(up, on_conflict="date,ticker").execute()
        updated += 1

    print(f"✅ backfilled price on {updated} of {len(rows)} event(s) for {d}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
