#!/usr/bin/env python3
"""
Read-only checks before deleting any local `outputs/` tree:

1. No `documents.document_key` still contains the legacy `outputs/` path prefix.
2. Optional: given --date (repeatable), a `daily_snapshots` row exists for that date.

Requires SUPABASE_URL + SUPABASE_SERVICE_KEY (e.g. config/supabase.env).

Exit 0 if all checks pass; non-zero if legacy keys remain or a requested date is missing.
"""
from __future__ import annotations

import argparse
import os
import sys
from pathlib import Path

try:
    from supabase import create_client  # type: ignore

    _HAS_SB = True
except ImportError:
    _HAS_SB = False

try:
    from dotenv import load_dotenv  # type: ignore

    load_dotenv(Path(__file__).resolve().parent.parent / "config" / "supabase.env")
    load_dotenv()
except ImportError:
    pass


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument(
        "--date",
        action="append",
        default=[],
        metavar="YYYY-MM-DD",
        help="Require a daily_snapshots row for this date (repeatable)",
    )
    args = ap.parse_args()

    if not _HAS_SB:
        print("❌ pip install supabase", file=sys.stderr)
        return 2

    url = os.environ.get("SUPABASE_URL")
    key = os.environ.get("SUPABASE_SERVICE_KEY")
    if not url or not key:
        print("❌ SUPABASE_URL and SUPABASE_SERVICE_KEY required (see config/supabase.env)", file=sys.stderr)
        return 2

    sb = create_client(url, key)

    # Legacy path keys should have been normalized by migration 009; catch stragglers.
    res = (
        sb.table("documents")
        .select("date,document_key")
        .like("document_key", "%outputs/%")
        .limit(200)
        .execute()
    )
    bad = getattr(res, "data", None) or []
    if bad:
        print("❌ documents.document_key still contains 'outputs/' (fix DB or re-run normalization):", file=sys.stderr)
        for row in bad[:50]:
            print(f"   {row.get('date')}  {row.get('document_key')}", file=sys.stderr)
        if len(bad) > 50:
            print(f"   … and {len(bad) - 50} more", file=sys.stderr)
        return 1
    print("✅ No documents.document_key values contain 'outputs/'")

    for d in args.date:
        snap = (
            sb.table("daily_snapshots")
            .select("date,run_type")
            .eq("date", d)
            .limit(1)
            .execute()
        )
        rows = getattr(snap, "data", None) or []
        if not rows:
            print(f"❌ No daily_snapshots row for {d}", file=sys.stderr)
            return 1
        print(f"✅ daily_snapshots row exists for {d} ({rows[0].get('run_type')})")

    print("✅ verify_supabase_canonical.py — OK")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
