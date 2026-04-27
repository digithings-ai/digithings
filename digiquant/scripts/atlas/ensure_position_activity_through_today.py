#!/usr/bin/env python3
"""
Bring `position_events` (Activity ledger) forward through a target date.

The weekday price job only runs refresh_performance_metrics — it does **not** insert
ledger rows. This script chains the recommended repair:

  1. (Optional) `refresh_performance_metrics.py --fill-calendar-through` so `positions`
     exists for each calendar day (carry-forward book).
  2. `backfill_position_events.py` — runs execute_at_open per missing trading day
     (rebalance_decision + HOLD from rebalance_table / positions).
  3. `reconcile_position_events_from_positions.py` — inserts HOLD only where a ticker
     on `positions` still has no `(date,ticker)` row.

Usage (repo root, SUPABASE_URL + SUPABASE_SERVICE_KEY set):

  python3 scripts/ensure_position_activity_through_today.py
  python3 scripts/ensure_position_activity_through_today.py --through 2026-04-15
  python3 scripts/ensure_position_activity_through_today.py --from 2026-04-11 --through 2026-04-15
  python3 scripts/ensure_position_activity_through_today.py --no-refresh   # skip step 1
  python3 scripts/ensure_position_activity_through_today.py --dry-run

See also: RUNBOOK.md § "Activity tab / position_events stops at an old date".
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


def _max_event_date(sb):
    res = sb.table("position_events").select("date").order("date", desc=True).limit(1).execute()
    rows = getattr(res, "data", None) or []
    if not rows:
        return None
    d = rows[0].get("date")
    return str(d)[:10] if d else None


def _next_calendar_day(iso: str) -> dt_date:
    y, m, d = map(int, iso.split("-"))
    return dt_date(y, m, d) + timedelta(days=1)


def main() -> int:
    root = Path(__file__).resolve().parents[1]
    py = sys.executable
    refresh = root / "scripts" / "refresh_performance_metrics.py"
    backfill = root / "scripts" / "backfill_position_events.py"
    reconcile = root / "scripts" / "reconcile_position_events_from_positions.py"

    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument(
        "--through",
        default=None,
        help="Last date to process YYYY-MM-DD (default: UTC today)",
    )
    ap.add_argument(
        "--from",
        dest="from_date",
        default=None,
        help="First date for backfill/reconcile (default: day after max(position_events.date))",
    )
    ap.add_argument(
        "--no-refresh",
        action="store_true",
        help="Skip refresh_performance_metrics --fill-calendar-through (use if positions rows already exist)",
    )
    ap.add_argument("--dry-run", action="store_true", help="Print planned commands only")
    args = ap.parse_args()

    through_s = args.through or dt_date.today().isoformat()
    through_d = dt_date.fromisoformat(through_s)

    sb = _sb()
    mx = _max_event_date(sb)

    if args.from_date:
        start_d = dt_date.fromisoformat(args.from_date)
    elif mx:
        start_d = _next_calendar_day(mx)
    else:
        print(
            "No rows in position_events — pass --from YYYY-MM-DD explicitly.",
            file=sys.stderr,
        )
        return 2

    if start_d > through_d:
        print(f"Nothing to do: ledger start {start_d} is after --through {through_d}")
        if not args.no_refresh and not args.dry_run:
            print("(Still running refresh step if you add --through later.)")
        start_s = None
    else:
        start_s = start_d.isoformat()

    steps: list[tuple[str, list[str]]] = []

    if not args.no_refresh:
        steps.append(
            (
                "Carry-forward positions + metrics through calendar",
                [
                    py,
                    str(refresh),
                    "--supabase",
                    "--fill-calendar-through",
                    through_s,
                ],
            )
        )

    if start_s:
        bf_cmd = [py, str(backfill), "--through", through_s, "--from", start_s]
        rec_cmd = [py, str(reconcile), "--from", start_s, "--through", through_s]
        if args.dry_run:
            bf_cmd.append("--dry-run")
            rec_cmd.append("--dry-run")
        steps.append(("Backfill position_events (execute_at_open per day)", bf_cmd))
        steps.append(("Reconcile missing HOLD rows from positions", rec_cmd))

    print(f"Target through: {through_s}")
    print(f"Max position_events.date before repair: {mx or '(none)'}")
    if start_s:
        print(f"Gap fill range: {start_s} → {through_s}")
    else:
        print("No gap fill for position_events (start after through).")

    for title, cmd in steps:
        print(f"\n=== {title} ===")
        print(" ", " ".join(cmd))
        if args.dry_run:
            continue
        r = subprocess.run(cmd, cwd=str(root), capture_output=False, text=True)
        if r.returncode != 0:
            print(f"❌ Step failed: {title} (exit {r.returncode})", file=sys.stderr)
            return r.returncode

    if args.dry_run:
        print("\n[dry-run] No commands executed.")
    else:
        mx_after = _max_event_date(sb)
        print("\n✅ ensure_position_activity_through_today finished.")
        print(f"Max position_events.date after repair: {mx_after or '(none)'}")
    return 0


if __name__ == "__main__":
    try:
        raise SystemExit(main())
    except Exception as ex:
        print(f"❌ {ex}", file=sys.stderr)
        sys.exit(1)
