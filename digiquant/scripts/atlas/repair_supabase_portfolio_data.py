#!/usr/bin/env python3
"""
repair_supabase_portfolio_data.py

Removes zero-weight non-CASH rows from `positions` (stale EXIT placeholders),
then re-runs `update_tearsheet.py` to rebuild nav_history, portfolio_metrics,
and upserts from local digests.

Usage:
  python3 scripts/repair_supabase_portfolio_data.py [--dry-run]

Environment: SUPABASE_URL, SUPABASE_SERVICE_KEY (see config/supabase.env)
"""

from __future__ import annotations

import argparse
import os
import subprocess
import sys
from pathlib import Path

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

ROOT = Path(__file__).parent.parent


def _sb():
    if not _HAS_SB:
        raise RuntimeError("pip install supabase")
    url = os.environ.get("SUPABASE_URL")
    key = os.environ.get("SUPABASE_SERVICE_KEY")
    if not url or not key:
        raise RuntimeError("SUPABASE_URL and SUPABASE_SERVICE_KEY required")
    return create_client(url, key)


def main() -> int:
    parser = argparse.ArgumentParser(description="Repair positions + refresh ETL from digests")
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="List rows that would be deleted without deleting or re-running ETL",
    )
    args = parser.parse_args()

    sb = _sb()

    res = (
        sb.table("positions")
        .select("date,ticker,weight_pct")
        .neq("ticker", "CASH")
        .eq("weight_pct", 0)
        .execute()
    )
    rows = getattr(res, "data", None) or []
    print(f"Found {len(rows)} zero-weight non-CASH position row(s).")
    for r in rows[:50]:
        print(f"  — {r.get('date')} {r.get('ticker')} weight_pct={r.get('weight_pct')}")
    if len(rows) > 50:
        print(f"  … and {len(rows) - 50} more")

    if args.dry_run:
        return 0

    if not rows:
        print("Nothing to delete; still running update_tearsheet to refresh metrics/NAV.")
    else:
        sb.table("positions").delete().neq("ticker", "CASH").eq("weight_pct", 0).execute()
        print("Deleted zero-weight non-CASH position rows.")

    ts = ROOT / "scripts" / "update_tearsheet.py"
    print(f"Running: {sys.executable} {ts}")
    r = subprocess.run([sys.executable, str(ts)], cwd=str(ROOT))
    return int(r.returncode)


if __name__ == "__main__":
    sys.exit(main())
