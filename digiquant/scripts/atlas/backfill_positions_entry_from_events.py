#!/usr/bin/env python3
"""
Back-fill positions.entry_price and entry_date from position_events (earliest OPEN/ADD with a mark).

Use after events exist but sync_positions_from_rebalance left nulls, or to repair history.

Usage:
  python3 scripts/backfill_positions_entry_from_events.py --date 2026-04-15
  python3 scripts/backfill_positions_entry_from_events.py --recent-days 60
  python3 scripts/backfill_positions_entry_from_events.py --recent-days 120 --dry-run

Environment: SUPABASE_URL, SUPABASE_SERVICE_KEY (see config/supabase.env)
"""

from __future__ import annotations

import argparse
import os
import sys
from pathlib import Path
from typing import Any, List, Set

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

from position_entry_from_events import patch_positions_entries_for_date


def _sb() -> Any:
    if not _HAS_SB:
        raise RuntimeError("pip install supabase")
    url = os.environ.get("SUPABASE_URL")
    key = os.environ.get("SUPABASE_SERVICE_KEY")
    if not url or not key:
        raise RuntimeError("SUPABASE_URL and SUPABASE_SERVICE_KEY required")
    return create_client(url, key)


def _distinct_position_dates(sb: Any, limit_rows: int = 8000) -> List[str]:
    """Recent snapshot dates from positions (descending)."""
    res = sb.table("positions").select("date").order("date", desc=True).limit(limit_rows).execute()
    rows = getattr(res, "data", None) or []
    seen: Set[str] = set()
    out: List[str] = []
    for r in rows:
        d = r.get("date")
        if not d:
            continue
        ds = str(d)[:10]
        if ds not in seen:
            seen.add(ds)
            out.append(ds)
    return out


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--date", help="Single positions snapshot date (YYYY-MM-DD)")
    ap.add_argument(
        "--recent-days",
        type=int,
        metavar="N",
        help="Patch up to N most recent distinct snapshot dates (default if no --date)",
    )
    ap.add_argument("--dry-run", action="store_true", help="Print counts only; do not write")
    args = ap.parse_args()

    sb = _sb()

    if args.date:
        dates = [args.date]
    else:
        n = args.recent_days if args.recent_days is not None else 30
        all_d = _distinct_position_dates(sb)
        dates = all_d[: max(1, min(n, len(all_d)))]

    total = 0
    for d in dates:
        if args.dry_run:
            res = (
                sb.table("positions")
                .select("ticker,entry_price")
                .eq("date", d)
                .execute()
            )
            need = 0
            for r in getattr(res, "data", None) or []:
                t = r.get("ticker")
                if not t or t == "CASH":
                    continue
                ep = r.get("entry_price")
                try:
                    ok = ep is not None and float(ep) > 0
                except (TypeError, ValueError):
                    ok = False
                if not ok:
                    need += 1
            print(f"{d}  would scan {need} row(s) needing entry_price")
            continue
        n = patch_positions_entries_for_date(sb, d)
        if n:
            print(f"{d}  updated {n} row(s)")
        total += n

    if not args.dry_run:
        print(f"Done. Total rows updated: {total}")
    return 0


if __name__ == "__main__":
    try:
        raise SystemExit(main())
    except Exception as ex:
        print(f"❌ {ex}", file=sys.stderr)
        sys.exit(1)
