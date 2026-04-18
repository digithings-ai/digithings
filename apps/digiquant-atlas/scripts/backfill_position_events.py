#!/usr/bin/env python3
"""
Backfill missing position_events by running the same logic as execute_at_open.py
for each trading day from --from through --through (inclusive).

Default --from: the calendar day after max(position_events.date) in Supabase.
Requires: SUPABASE_URL, SUPABASE_SERVICE_KEY, rebalance_decision.json per day (or
prior-trading-day mode when same-day doc is missing).

After inserts with possible null opens, runs backfill_execution_prices.py for that date.

Usage:
  python3 scripts/backfill_position_events.py --through 2026-04-15
  python3 scripts/backfill_position_events.py --from 2026-04-07 --through 2026-04-13 --dry-run
"""

from __future__ import annotations

import argparse
import os
import subprocess
import sys
from datetime import date as dt_date, timedelta
from pathlib import Path

try:
    from dotenv import load_dotenv  # type: ignore

    load_dotenv(Path(__file__).parent.parent / "config" / "supabase.env")
    load_dotenv()
except ImportError:
    pass

try:
    from supabase import create_client  # type: ignore

    _HAS_SB = True
except ImportError:
    _HAS_SB = False


def _sb():
    if not _HAS_SB:
        raise RuntimeError("pip install supabase")
    url = os.environ.get("SUPABASE_URL")
    key = os.environ.get("SUPABASE_SERVICE_KEY")
    if not url or not key:
        raise RuntimeError("SUPABASE_URL and SUPABASE_SERVICE_KEY required")
    return create_client(url, key)


def _iter_trading_days(start: dt_date, end: dt_date) -> list[str]:
    out: list[str] = []
    cur = start
    while cur <= end:
        if cur.weekday() < 5:
            out.append(cur.isoformat())
        cur += timedelta(days=1)
    return out


def _max_event_date(sb):
    res = sb.table("position_events").select("date").order("date", desc=True).limit(1).execute()
    rows = getattr(res, "data", None) or []
    if not rows:
        return None
    return rows[0].get("date")


def _next_calendar_day(iso: str) -> dt_date:
    y, m, d = map(int, iso.split("-"))
    return dt_date(y, m, d) + timedelta(days=1)


def main() -> int:
    ap = argparse.ArgumentParser(
        description="Backfill position_events for missing trading days using execute_at_open."
    )
    ap.add_argument(
        "--from",
        dest="from_date",
        default=None,
        help="Start date YYYY-MM-DD (default: day after max position_events.date)",
    )
    ap.add_argument(
        "--through",
        default=dt_date.today().isoformat(),
        help="Last date to process (default: UTC today)",
    )
    ap.add_argument(
        "--dry-run",
        action="store_true",
        help="Print dates and commands only",
    )
    ap.add_argument(
        "--skip-price-backfill",
        action="store_true",
        help="Do not run backfill_execution_prices.py after each day with new events",
    )
    args = ap.parse_args()

    root = Path(__file__).resolve().parents[1]
    exe_script = root / "scripts" / "execute_at_open.py"
    price_script = root / "scripts" / "backfill_execution_prices.py"
    py = sys.executable

    sb = _sb()
    through_d = dt_date.fromisoformat(args.through)

    if args.from_date:
        start_d = dt_date.fromisoformat(args.from_date)
    else:
        mx = _max_event_date(sb)
        if not mx:
            print("No rows in position_events; pass --from YYYY-MM-DD explicitly.", file=sys.stderr)
            return 2
        start_d = _next_calendar_day(mx)

    if start_d > through_d:
        print(f"Nothing to do: start {start_d} is after --through {through_d}")
        return 0

    days = _iter_trading_days(start_d, through_d)
    if not days:
        print("No trading days in range.")
        return 0

    print(f"Backfill {len(days)} trading day(s): {days[0]} … {days[-1]}")

    for d in days:
        print(f"\n--- {d} ---")
        if args.dry_run:
            print(f"  [dry-run] {py} {exe_script} --date {d}")
            print(f"  [dry-run] {py} {exe_script} --date {d} --prior-trading-day-rebalance  (if needed)")
            continue

        # 1) Same-day rebalance_decision
        r1 = subprocess.run(
            [py, str(exe_script), "--date", d],
            cwd=str(root),
            capture_output=True,
            text=True,
        )
        out1 = (r1.stdout or "") + (r1.stderr or "")
        print(out1.rstrip())

        need_prior = "No rebalance_decision payload" in out1 or "No rebalance_decision" in out1
        out2 = ""
        if need_prior:
            r2 = subprocess.run(
                [py, str(exe_script), "--date", d, "--prior-trading-day-rebalance"],
                cwd=str(root),
                capture_output=True,
                text=True,
            )
            out2 = (r2.stdout or "") + (r2.stderr or "")
            print(out2.rstrip())

        combined = out1 + out2
        wrote = "recorded" in combined.lower()
        if not args.skip_price_backfill and wrote:
            r3 = subprocess.run(
                [py, str(price_script), "--date", d],
                cwd=str(root),
                capture_output=True,
                text=True,
            )
            po = (r3.stdout or "").strip()
            if po:
                print(po)

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
