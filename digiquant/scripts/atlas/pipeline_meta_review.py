#!/usr/bin/env python3
"""
List recent `pipeline_review` documents in Supabase `documents` (optional weekly operator hook).

Does not create GitHub Issues by default (extend when you want a weekly digest issue).

Usage:
  python3 scripts/pipeline_meta_review.py --days 14
"""

from __future__ import annotations

import argparse
import os
import sys
from datetime import date, timedelta
from pathlib import Path
from typing import Any, Dict, List

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


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument(
        "--days",
        type=int,
        default=14,
        help="Look back this many calendar days from today (default: 14)",
    )
    args = ap.parse_args()

    sb = _sb()
    end_d = date.today()
    start_d = end_d - timedelta(days=max(1, args.days))
    start_s = start_d.isoformat()

    res = (
        sb.table("documents")
        .select("date,document_key,title,payload")
        .gte("date", start_s)
        .like("document_key", "pipeline-review/%")
        .order("date", desc=True)
        .execute()
    )
    rows: List[Dict[str, Any]] = getattr(res, "data", None) or []
    print(f"pipeline_review documents since {start_s}: {len(rows)}")
    for r in rows:
        p = r.get("payload")
        dt = ""
        if isinstance(p, dict):
            dt = str(p.get("doc_type") or "")
        print(f"  {r.get('date')}  {r.get('document_key')}  title={r.get('title')}  payload.doc_type={dt}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
