#!/usr/bin/env python3
"""
Fill position_events.price from the execution day's open when it ran before opens existed.

Typical flow: pre-market run_db_first → execute_at_open records events with price=null →
after the session (or after the R2 generation seals, or via the same-day live open), run
this script for that date. Sealed dates read the R2 generations; unsealed (same-day)
opens come from the live fetch (#4053 D1).

Usage:
  python3 scripts/backfill_execution_prices.py [--date YYYY-MM-DD]
Environment: SUPABASE_URL, SUPABASE_SERVICE_ROLE_KEY (position_events read/write only)
"""

from __future__ import annotations

import argparse
import math
import os
from datetime import date as dt_date
from pathlib import Path
from typing import Any, Dict, List, Optional

from digiquant.dashboard.tenancy import house_workspace_id
from digiquant.research.data.queries import (
    r2_manifest_seal,
    r2_ohlcv_rows,
)

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
    url = os.environ.get("CORE_SUPABASE_URL", os.environ.get("SUPABASE_URL"))
    key = os.environ.get("CORE_SUPABASE_SERVICE_KEY", os.environ.get("SUPABASE_SERVICE_ROLE_KEY"))
    if not url or not key:
        raise RuntimeError("SUPABASE_URL and SUPABASE_SERVICE_ROLE_KEY required")
    return create_client(url, key)


def _fetch_open(sb, ticker: str, d: str) -> Optional[float]:
    day = str(d)[:10]
    seal, _ = r2_manifest_seal()
    if day <= seal.isoformat():
        try:
            rows = r2_ohlcv_rows(tickers=[ticker], since=day, until=day)
        except LookupError:
            return None
        if not rows or rows[0].get("open") is None:
            return None
        try:
            price = float(rows[0]["open"])
        except (TypeError, ValueError):
            return None
        return price if math.isfinite(price) and price > 0 else None
    # Same-day (unsealed) opens have no sealed R2 bar yet — fetch live (#4053 D1).
    # Never raises into the backfill: a failed fetch is None (row stays null).
    try:
        from digiquant.data.prices.live_opens import fetch_live_open
    except Exception:
        return None
    try:
        return fetch_live_open(ticker, day)
    except Exception:
        return None


def _house_id() -> str:
    return str(house_workspace_id())


def _eq_house(query: Any) -> Any:
    return query.eq("workspace_id", _house_id())


def backfill_prices_for_date(sb: Any, d: str) -> int:
    """Fill null ``position_events.price`` from the day's open for house rows."""
    res = (
        _eq_house(sb.table("position_events").select("date,ticker,event,price,weight_pct,reason,thesis_id"))
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
            print(f"   skip {ticker}: no open for {d}")
            continue
        up = {
            "workspace_id": _house_id(),
            "date": d,
            "ticker": str(ticker),
            "event": row.get("event"),
            "weight_pct": row.get("weight_pct"),
            "price": px,
            "reason": row.get("reason"),
            "thesis_id": row.get("thesis_id"),
        }
        sb.table("position_events").upsert(up, on_conflict="workspace_id,date,ticker").execute()
        updated += 1

    print(f"✅ backfilled price on {updated} of {len(rows)} event(s) for {d}")
    return updated


def main() -> int:
    ap = argparse.ArgumentParser(description="Backfill position_events.price from the day's open.")
    ap.add_argument("--date", default=dt_date.today().isoformat(), help="YYYY-MM-DD")
    args = ap.parse_args()
    return 0 if backfill_prices_for_date(_sb(), args.date) >= 0 else 1


if __name__ == "__main__":
    raise SystemExit(main())
