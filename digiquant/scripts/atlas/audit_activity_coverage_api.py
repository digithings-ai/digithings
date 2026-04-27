#!/usr/bin/env python3
"""
Same checks as scripts/sql/audit_activity_coverage.sql using the Supabase REST client
(SUPABASE_URL + SUPABASE_SERVICE_KEY — no Postgres URI required).

Usage:
  python3 scripts/audit_activity_coverage_api.py
"""

from __future__ import annotations

import os
import sys
from pathlib import Path

try:
    from dotenv import load_dotenv

    load_dotenv(Path(__file__).resolve().parents[1] / "config" / "supabase.env")
    load_dotenv()
except ImportError:
    pass

try:
    from supabase import create_client
except ImportError:
    print("pip install supabase", file=sys.stderr)
    sys.exit(1)


def _max_date(sb, table: str, col: str = "date"):
    r = sb.table(table).select(col).order(col, desc=True).limit(1).execute()
    rows = getattr(r, "data", None) or []
    if not rows:
        return None
    v = rows[0].get(col)
    return str(v)[:10] if v else None


def main() -> int:
    url = os.environ.get("SUPABASE_URL")
    key = os.environ.get("SUPABASE_SERVICE_KEY")
    if not url or not key:
        print("SUPABASE_URL and SUPABASE_SERVICE_KEY required", file=sys.stderr)
        return 1
    sb = create_client(url, key)
    pe = _max_date(sb, "position_events")
    pos = _max_date(sb, "positions")
    nav = _max_date(sb, "nav_history")
    ds = _max_date(sb, "daily_snapshots")
    print("max_position_events_date ", pe)
    print("max_positions_date       ", pos)
    print("max_nav_history_date     ", nav)
    print("max_daily_snapshots_date ", ds)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
