#!/usr/bin/env python3
"""
publish_research.py — Publish a research note (markdown) to Supabase documents.

Stores research notes in the documents table under the research/ namespace.
category is set to 'deep-dive' (valid constraint value). Markdown content is
stored in documents.content; payload holds structured metadata.

Document key patterns:
  research/deep-dives/{TICKER}-{DATE}     e.g. research/deep-dives/NVDA-2026-04-14
  research/papers/{SLUG}                  e.g. research/papers/macro-regime
  research/concepts/{SLUG}                e.g. research/concepts/dual-momentum
  research/themes/{SLUG}-{DATE}           e.g. research/themes/ai-capex-cycle-2026-04-14

Usage:
    # From a markdown file
    python3 scripts/publish_research.py \\
        --file data/agent-cache/deep-dives/NVDA-2026-04-14.md \\
        --key research/deep-dives/NVDA-2026-04-14 \\
        --title "NVDA Deep Dive" \\
        --type deep-dive \\
        --date 2026-04-14

    # From stdin (agent pipes markdown directly)
    cat note.md | python3 scripts/publish_research.py \\
        --content - \\
        --key research/concepts/momentum-factor \\
        --title "Momentum Factor Notes" \\
        --type concept

    # List existing research library
    python3 scripts/publish_research.py --list
"""
from __future__ import annotations

import argparse
import json
import os
import sys
from datetime import date as dt_date
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


def _load_content(file_or_dash: str) -> str:
    if file_or_dash == "-":
        content = sys.stdin.read()
        if not content.strip():
            raise ValueError("stdin is empty")
        return content
    return Path(file_or_dash).read_text(encoding="utf-8")


def cmd_publish(args: argparse.Namespace) -> int:
    content_src = args.file or args.content
    if not content_src:
        print("error: provide --file <path> or --content -", file=sys.stderr)
        return 1

    content = _load_content(content_src)
    date_str = args.date or str(dt_date.today())

    payload = {
        "date": date_str,
        "research_type": args.type,
        "title": args.title,
        "document_key": args.key,
        "tags": args.tags or [],
        "ticker": args.ticker or None,
    }

    row = {
        "date": date_str,
        "title": args.title,
        "doc_type": "Deep Dive",
        "phase": None,
        "category": "deep-dive",
        "segment": args.type,
        "sector": None,
        "run_type": None,
        "document_key": args.key,
        "payload": payload,
        "content": content,
    }

    sb = _sb()
    sb.table("documents").upsert(row, on_conflict="date,document_key").execute()
    print(f"published documents:{date_str}/{args.key}")
    return 0


def cmd_list(args: argparse.Namespace) -> int:
    sb = _sb()
    res = (
        sb.table("documents")
        .select("date,document_key,title,doc_type,segment")
        .like("document_key", "research/%")
        .order("date", desc=True)
        .limit(args.limit)
        .execute()
    )
    rows = res.data or []
    if not rows:
        print("No research documents found.")
        return 0

    # Group by segment/type
    by_type: dict[str, list] = {}
    for r in rows:
        seg = r.get("segment") or "other"
        by_type.setdefault(seg, []).append(r)

    for seg, items in sorted(by_type.items()):
        print(f"\n## {seg}")
        for item in items:
            print(f"  [{item['date']}] {item['document_key']} — {item['title']}")
    return 0


def main() -> int:
    ap = argparse.ArgumentParser(description="Publish or list research notes in Supabase.")
    sub = ap.add_subparsers(dest="cmd")

    # publish (default when --key is present)
    ap.add_argument("--key", help="document_key e.g. research/deep-dives/NVDA-2026-04-14")
    ap.add_argument("--title", help="Human-readable title")
    ap.add_argument("--type", default="deep-dive",
                    choices=["deep-dive", "paper", "concept", "theme", "sector", "macro"],
                    help="Research note type (paper = static doctrine; deep-dive = dated analysis)")
    ap.add_argument("--file", help="Path to markdown file")
    ap.add_argument("--content", help="'-' to read markdown from stdin")
    ap.add_argument("--date", help="YYYY-MM-DD (default: today)")
    ap.add_argument("--ticker", help="Primary ticker if applicable")
    ap.add_argument("--tags", nargs="*", help="Optional tag list")
    ap.add_argument("--list", action="store_true", help="List research library index")
    ap.add_argument("--limit", type=int, default=100, help="Max rows to list")

    args = ap.parse_args()

    if args.list:
        return cmd_list(args)

    if not args.key or not args.title:
        ap.print_help()
        return 1

    return cmd_publish(args)


if __name__ == "__main__":
    sys.exit(main())
