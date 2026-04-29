#!/usr/bin/env python3
"""
Insert missing `position_events` rows as HOLD for every `positions` line (weight > 0) on a
session date when no `(date, ticker)` ledger row exists yet. Does not overwrite existing
events (OPEN/TRIM/ADD/EXIT/HOLD).

Use when `rebalance_table` omitted tickers that still appear in `positions`, or after
repairing historical data.

Requires: SUPABASE_URL, SUPABASE_SERVICE_KEY

Usage:
  python3 scripts/reconcile_position_events_from_positions.py --from 2026-01-02 --through 2026-04-15
  python3 scripts/reconcile_position_events_from_positions.py --from 2026-04-01 --through 2026-04-15 --dry-run
"""

from __future__ import annotations

import argparse
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

sys.path.insert(0, str(Path(__file__).resolve().parent))
import execute_at_open as eat  # noqa: E402


def _iter_trading_days(start: dt_date, end: dt_date) -> list[str]:
    out: list[str] = []
    cur = start
    while cur <= end:
        if cur.weekday() < 5:
            out.append(cur.isoformat())
        cur += timedelta(days=1)
    return out


def main() -> int:
    ap = argparse.ArgumentParser(
        description="Upsert HOLD rows in position_events for positions rows missing a ledger line."
    )
    ap.add_argument("--from", dest="from_date", required=True, help="Start date YYYY-MM-DD")
    ap.add_argument(
        "--through",
        default=dt_date.today().isoformat(),
        help="Last date to process (default: UTC today)",
    )
    ap.add_argument("--dry-run", action="store_true", help="Print planned upserts only")
    ap.add_argument(
        "--skip-price-backfill",
        action="store_true",
        help="Do not run backfill_execution_prices.py after days with new rows",
    )
    args = ap.parse_args()

    root = Path(__file__).resolve().parents[1]
    price_script = root / "scripts" / "backfill_execution_prices.py"
    py = sys.executable

    start_d = dt_date.fromisoformat(args.from_date)
    through_d = dt_date.fromisoformat(args.through)
    if start_d > through_d:
        print(f"Nothing to do: --from {start_d} is after --through {through_d}")
        return 0

    days = _iter_trading_days(start_d, through_d)
    if not days:
        print("No trading days in range.")
        return 0

    sb = eat._sb()
    print(f"Reconcile {len(days)} trading day(s): {days[0]} … {days[-1]}")

    total = 0
    for d in days:
        existing = eat._event_tickers_for_date(sb, d)
        holds = eat._hold_events_for_positions_not_in_rebalance(sb, d, existing)
        if not holds:
            continue
        tickers = ", ".join(h["ticker"] for h in holds)
        if args.dry_run:
            print(f"  {d}: would upsert {len(holds)} HOLD — {tickers}")
            total += len(holds)
            continue
        for e in holds:
            sb.table("position_events").upsert(e, on_conflict="date,ticker").execute()
        print(f"  {d}: upserted {len(holds)} HOLD — {tickers}")
        total += len(holds)
        null_px = sum(1 for e in holds if e.get("price") is None)
        if null_px and not args.skip_price_backfill:
            r = subprocess.run(
                [py, str(price_script), "--date", d],
                cwd=str(root),
                capture_output=True,
                text=True,
            )
            po = (r.stdout or "").strip()
            if po:
                print(po)

    if args.dry_run:
        print(f"[dry-run] {total} HOLD row(s) would be written.")
    else:
        print(f"Done. {total} HOLD row(s) upserted.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
