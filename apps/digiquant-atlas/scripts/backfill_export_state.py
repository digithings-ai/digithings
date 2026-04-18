#!/usr/bin/env python3
"""
backfill_export_state.py — Pre-backfill Supabase state export (rollback aid).

Exports daily_snapshots + documents rows for a date range to JSON files so
the operator can restore if the backfill produces bad results.

Usage:
    python3 scripts/backfill_export_state.py --start 2026-04-05 --end 2026-04-14
    python3 scripts/backfill_export_state.py --start 2026-04-05 --end 2026-04-14 --out data/backfill-backup
"""

from __future__ import annotations

import argparse
import json
import os
import sys
from datetime import date, timedelta
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

ROOT = Path(__file__).parent.parent
DEFAULT_OUT = ROOT / "data" / "backfill-backup"


def _sb():
    if not _HAS_SB:
        raise RuntimeError("pip install supabase")
    url = os.environ.get("SUPABASE_URL")
    key = os.environ.get("SUPABASE_SERVICE_KEY")
    if not url or not key:
        raise RuntimeError("SUPABASE_URL + SUPABASE_SERVICE_KEY required")
    return create_client(url, key)


def _date_range(start: str, end: str) -> list[str]:
    d = date.fromisoformat(start)
    e = date.fromisoformat(end)
    out = []
    while d <= e:
        out.append(d.isoformat())
        d += timedelta(days=1)
    return out


def export_state(start: str, end: str, out_dir: Path) -> None:
    sb = _sb()
    out_dir.mkdir(parents=True, exist_ok=True)

    # daily_snapshots
    res = (
        sb.table("daily_snapshots")
        .select("*")
        .gte("date", start)
        .lte("date", end)
        .order("date")
        .execute()
    )
    snap_rows = getattr(res, "data", None) or []
    snap_path = out_dir / "daily_snapshots.json"
    snap_path.write_text(json.dumps(snap_rows, indent=2, ensure_ascii=False), encoding="utf-8")
    print(f"✅ Exported {len(snap_rows)} daily_snapshots rows → {snap_path}")

    # documents
    res2 = (
        sb.table("documents")
        .select("*")
        .gte("date", start)
        .lte("date", end)
        .order("date,document_key")
        .execute()
    )
    doc_rows = getattr(res2, "data", None) or []
    doc_path = out_dir / "documents.json"
    doc_path.write_text(json.dumps(doc_rows, indent=2, ensure_ascii=False), encoding="utf-8")
    print(f"✅ Exported {len(doc_rows)} documents rows → {doc_path}")

    # positions
    res3 = (
        sb.table("positions")
        .select("*")
        .gte("date", start)
        .lte("date", end)
        .order("date,ticker")
        .execute()
    )
    pos_rows = getattr(res3, "data", None) or []
    pos_path = out_dir / "positions.json"
    pos_path.write_text(json.dumps(pos_rows, indent=2, ensure_ascii=False), encoding="utf-8")
    print(f"✅ Exported {len(pos_rows)} positions rows → {pos_path}")

    summary = {
        "exported_at": __import__("datetime").datetime.utcnow().isoformat() + "Z",
        "start": start,
        "end": end,
        "daily_snapshots_count": len(snap_rows),
        "documents_count": len(doc_rows),
        "positions_count": len(pos_rows),
    }
    (out_dir / "export_summary.json").write_text(
        json.dumps(summary, indent=2), encoding="utf-8"
    )
    print(f"📦 Backup complete → {out_dir}/")


def main() -> int:
    ap = argparse.ArgumentParser(description="Export Supabase state for a date range (pre-backfill backup).")
    ap.add_argument("--start", required=True, help="Start date YYYY-MM-DD")
    ap.add_argument("--end", required=True, help="End date YYYY-MM-DD")
    ap.add_argument("--out", default=str(DEFAULT_OUT), help="Output directory")
    args = ap.parse_args()

    try:
        export_state(args.start, args.end, Path(args.out))
        return 0
    except Exception as e:
        print(f"❌ {e}", file=sys.stderr)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
