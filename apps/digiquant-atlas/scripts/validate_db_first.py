#!/usr/bin/env python3
from __future__ import annotations

import argparse
import os
import sys
from datetime import date as dt_date
from pathlib import Path
from typing import Any, Dict, List, Optional

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


def _sb():
    if not _HAS_SB:
        raise RuntimeError("pip install supabase")
    url = os.environ.get("SUPABASE_URL")
    key = os.environ.get("SUPABASE_SERVICE_KEY")
    if not url or not key:
        raise RuntimeError("SUPABASE_URL and SUPABASE_SERVICE_KEY required")
    return create_client(url, key)


def _fail(msg: str) -> None:
    print(f"❌ {msg}", file=sys.stderr)


def _pass(msg: str) -> None:
    print(f"✅ {msg}")


def _has_research_delta(sb, d: str) -> bool:
    """True if any documents row for this date carries a research_delta payload (any document_key)."""
    res = sb.table("documents").select("payload").eq("date", d).limit(500).execute()
    for r in getattr(res, "data", None) or []:
        p = r.get("payload")
        if isinstance(p, dict) and p.get("doc_type") == "research_delta":
            return True
    return False


def _has_research_doc(sb, d: str) -> bool:
    res = (
        sb.table("documents")
        .select("payload,document_key")
        .eq("date", d)
        .limit(500)
        .execute()
    )
    for r in getattr(res, "data", None) or []:
        key = str(r.get("document_key") or "")
        p = r.get("payload")
        if key == "digest" and p is not None:
            return True
        if isinstance(p, dict) and p.get("doc_type") in (
            "research_delta",
            "document_delta",
            "research_changelog",
            "research_baseline_manifest",
        ):
            return True
        low = key.lower()
        if low.startswith("document-deltas/") or low.startswith("research-changelog/"):
            return True
    return False


def _has_rebalance_doc(sb, d: str) -> bool:
    res = (
        sb.table("documents")
        .select("payload")
        .eq("date", d)
        .eq("document_key", "rebalance-decision.json")
        .limit(1)
        .execute()
    )
    rows = getattr(res, "data", None) or []
    if not rows:
        return False
    p = rows[0].get("payload")
    return isinstance(p, dict) and p.get("doc_type") == "rebalance_decision"


def main() -> int:
    ap = argparse.ArgumentParser(description="DB-first validation for a run date.")
    ap.add_argument("--date", default=dt_date.today().isoformat(), help="YYYY-MM-DD")
    ap.add_argument(
        "--mode",
        choices=("full", "research", "pm"),
        default="full",
        help="full: digest + positions + metrics; research: snapshot + digest OR research_delta; pm: full + rebalance_decision. "
        "Stricter digest+schema: scripts/validate_pipeline_step.py --step research_closeout",
    )
    args = ap.parse_args()
    d = args.date
    mode = args.mode

    sb = _sb()
    fails = 0

    # daily_snapshots row exists
    snap = (
        sb.table("daily_snapshots")
        .select("date,run_type,snapshot")
        .eq("date", d)
        .limit(1)
        .execute()
    )
    srows = getattr(snap, "data", None) or []
    if not srows:
        _fail(f"daily_snapshots missing for {d}")
        fails += 1
    else:
        snap_val = srows[0].get("snapshot")
        if not isinstance(snap_val, dict):
            if mode == "research" and _has_research_delta(sb, d):
                _pass(f"daily_snapshots row for {d} (research_delta-only; snapshot json optional)")
            else:
                _fail(f"daily_snapshots.snapshot missing or not json for {d}")
                fails += 1
        else:
            _pass(f"daily_snapshots present for {d}")

    # digest OR research_delta (research track can publish without portfolio digest text)
    if mode == "research":
        if not _has_research_doc(sb, d):
            _fail(f"documents missing digest or research_delta payload for {d}")
            fails += 1
        else:
            _pass("documents: digest or research_delta present")
    else:
        doc = (
            sb.table("documents")
            .select("date,document_key,payload")
            .eq("date", d)
            .eq("document_key", "digest")
            .limit(1)
            .execute()
        )
        drows = getattr(doc, "data", None) or []
        if not drows:
            _fail(f"documents missing digest for {d}")
            fails += 1
        else:
            if drows[0].get("payload") is None:
                _fail(f"documents.digest payload null for {d}")
                fails += 1
            else:
                _pass(f"documents.digest present for {d}")

    if mode == "pm":
        if not _has_rebalance_doc(sb, d):
            _fail(f"documents missing rebalance_decision (rebalance-decision.json) for {d}")
            fails += 1
        else:
            _pass("documents.rebalance_decision present")

    # positions: no zero-weight non-CASH (skip for research-only days that did not touch positions)
    if mode != "research":
        pos = (
            sb.table("positions")
            .select("ticker,weight_pct")
            .eq("date", d)
            .neq("ticker", "CASH")
            .eq("weight_pct", 0)
            .execute()
        )
        prows = getattr(pos, "data", None) or []
        if prows:
            _fail(f"positions has {len(prows)} zero-weight non-CASH rows for {d}")
            fails += 1
        else:
            _pass("positions has no zero-weight non-CASH rows")

    # nav_history and portfolio_metrics: at least one row exists (we validate freshness elsewhere)
    nav = sb.table("nav_history").select("date").order("date", desc=True).limit(1).execute()
    if not (getattr(nav, "data", None) or []):
        _fail("nav_history empty")
        fails += 1
    else:
        _pass("nav_history non-empty")

    pm = sb.table("portfolio_metrics").select("date").order("date", desc=True).limit(1).execute()
    if not (getattr(pm, "data", None) or []):
        _fail("portfolio_metrics empty")
        fails += 1
    else:
        _pass("portfolio_metrics non-empty")

    return 1 if fails else 0


if __name__ == "__main__":
    raise SystemExit(main())

