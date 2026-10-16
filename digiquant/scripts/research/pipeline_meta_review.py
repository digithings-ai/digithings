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
from typing import Any, Dict, List  # score:allow untyped any — duck-typed PostgREST rows

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

_REPO_ROOT = Path(__file__).resolve().parents[3]


def _ensure_importable() -> None:
    path = str(_REPO_ROOT / "digiquant" / "src")
    if path not in sys.path:
        sys.path.insert(0, path)


_ensure_importable()
from digiquant.dashboard.tenancy import eq_house_workspace  # noqa: E402


def _sb():
    if not _HAS_SB:
        raise RuntimeError("pip install supabase")
    url = os.environ.get("CORE_SUPABASE_URL", os.environ.get("SUPABASE_URL"))
    key = os.environ.get("CORE_SUPABASE_SERVICE_KEY", os.environ.get("SUPABASE_SERVICE_ROLE_KEY"))
    if not url or not key:
        raise RuntimeError("SUPABASE_URL and SUPABASE_SERVICE_ROLE_KEY required")
    return create_client(url, key)


def house_pipeline_review_docs(sb: Any, start_s: str) -> List[Dict[str, Any]]:
    """House ``pipeline-review/%`` rows since ``start_s``. Overlay reviews stay private."""
    res = (
        eq_house_workspace(sb.table("documents").select("date,document_key,title,payload"))
        .gte("date", start_s)
        .like("document_key", "pipeline-review/%")
        .order("date", desc=True)
        .execute()
    )
    return list(getattr(res, "data", None) or [])


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

    rows = house_pipeline_review_docs(sb, start_s)
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
