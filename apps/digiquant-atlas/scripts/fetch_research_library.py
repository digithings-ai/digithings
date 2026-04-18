#!/usr/bin/env python3
"""
fetch_research_library.py — List or fetch research notes from Supabase.

Research notes are stored in documents table with category='research' and
document_key pattern: research/{type}/{slug}

Types: deep-dive, concept, theme, sector, macro

Usage:
    # Print index of all research docs
    python3 scripts/fetch_research_library.py

    # Print full content of a specific note
    python3 scripts/fetch_research_library.py --key research/deep-dives/NVDA-2026-04-14

    # Filter by type
    python3 scripts/fetch_research_library.py --type deep-dive

    # Filter by ticker
    python3 scripts/fetch_research_library.py --ticker NVDA

    # Cache all research docs to local scratch (for session preload)
    python3 scripts/fetch_research_library.py --cache data/agent-cache/research/
"""
from __future__ import annotations

import argparse
import os
import sys
from pathlib import Path

try:
    from supabase import create_client
    _HAS_SB = True
except ImportError:
    _HAS_SB = False

try:
    from dotenv import load_dotenv
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


def _query(sb, args: argparse.Namespace, select: str = "date,document_key,title,doc_type,segment,payload"):
    q = (
        sb.table("documents")
        .select(select)
        .like("document_key", "research/%")
        .order("date", desc=True)
    )
    if args.type:
        q = q.eq("segment", args.type)
    if args.ticker:
        # ticker stored in payload.ticker — use ilike on title as fallback
        q = q.ilike("title", f"%{args.ticker}%")
    if args.since:
        q = q.gte("date", args.since)
    return q.limit(args.limit).execute()


def cmd_index(args: argparse.Namespace) -> int:
    sb = _sb()
    res = _query(sb, args)
    rows = res.data or []
    if not rows:
        print("No research documents found.")
        return 0

    by_type: dict[str, list] = {}
    for r in rows:
        seg = r.get("segment") or "other"
        by_type.setdefault(seg, []).append(r)

    print("# Research Library Index (Supabase)\n")
    for seg in sorted(by_type):
        print(f"## {seg}")
        for item in by_type[seg]:
            print(f"  [{item['date']}] {item['document_key']}  —  {item['title']}")
        print()
    return 0


def cmd_fetch_one(args: argparse.Namespace) -> int:
    sb = _sb()
    res = (
        sb.table("documents")
        .select("date,document_key,title,content")
        .eq("document_key", args.key)
        .limit(1)
        .execute()
    )
    rows = res.data or []
    if not rows:
        print(f"Not found: {args.key}", file=sys.stderr)
        return 1
    r = rows[0]
    print(f"# {r['title']}  ({r['date']})\n")
    print(r.get("content") or "(no content)")
    return 0


def cmd_cache(args: argparse.Namespace) -> int:
    sb = _sb()
    res = _query(sb, args, select="date,document_key,title,content")
    rows = res.data or []
    if not rows:
        print("No research documents to cache.")
        return 0

    cache_dir = Path(args.cache)
    cache_dir.mkdir(parents=True, exist_ok=True)

    written = 0
    for r in rows:
        key = r["document_key"]  # e.g. research/deep-dives/NVDA-2026-04-14
        rel = key.removeprefix("research/")  # deep-dives/NVDA-2026-04-14
        out = cache_dir / (rel + ".md")
        out.parent.mkdir(parents=True, exist_ok=True)
        content = r.get("content") or f"# {r['title']}\n\n(no content)"
        out.write_text(content, encoding="utf-8")
        written += 1

    print(f"Cached {written} research notes to {cache_dir}")
    return 0


def main() -> int:
    ap = argparse.ArgumentParser(description="Fetch research library from Supabase.")
    ap.add_argument("--key", help="Fetch full content of one note by document_key")
    ap.add_argument("--type", help="Filter by type: deep-dive|concept|theme|sector|macro")
    ap.add_argument("--ticker", help="Filter by ticker (matches title)")
    ap.add_argument("--since", help="Filter by date >= YYYY-MM-DD")
    ap.add_argument("--limit", type=int, default=200)
    ap.add_argument("--cache", help="Cache all matching notes to this local directory")
    args = ap.parse_args()

    if args.key:
        return cmd_fetch_one(args)
    if args.cache:
        return cmd_cache(args)
    return cmd_index(args)


if __name__ == "__main__":
    sys.exit(main())
