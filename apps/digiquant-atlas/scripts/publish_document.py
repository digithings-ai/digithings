#!/usr/bin/env python3
from __future__ import annotations

import argparse
import json
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


def _render_markdown(payload: dict) -> str:
    # Keep backend renderer in one place for now (also used by update_tearsheet).
    # Import locally to avoid importing heavy deps at module import time.
    from scripts.update_tearsheet import _render_markdown_from_payload  # type: ignore

    return _render_markdown_from_payload(payload)


def _load_payload(path_or_dash: str) -> dict:
    if path_or_dash == "-":
        raw = sys.stdin.read()
        if not raw.strip():
            raise ValueError("stdin is empty (pass JSON for --payload -)")
        payload = json.loads(raw)
    else:
        payload = json.loads(Path(path_or_dash).read_text(encoding="utf-8"))
    if not isinstance(payload, dict):
        raise ValueError("payload must be a JSON object")
    return payload


def main() -> int:
    ap = argparse.ArgumentParser(description="Publish an artifact JSON payload into Supabase documents.")
    ap.add_argument(
        "--payload",
        required=True,
        help="Path to artifact JSON file, or '-' to read JSON from stdin (hosted / no repo-local files).",
    )
    ap.add_argument("--document-key", required=True, help="Stable key (e.g. 'weekly/2026-W15.json')")
    ap.add_argument("--title", required=True, help="Document title")
    ap.add_argument("--category", default="rollup", help="Category tag")
    ap.add_argument("--doc-type-label", default=None, help="Human label for documents.doc_type (optional)")
    ap.add_argument("--date", default=None, help="Override date (YYYY-MM-DD); default from payload.date")
    ap.add_argument("--no-markdown", action="store_true", help="Do not render/store documents.content")
    args = ap.parse_args()

    payload = _load_payload(args.payload)

    date_str = args.date or str(payload.get("date") or "")
    if not date_str:
        raise ValueError("Missing date (pass --date or include payload.date)")

    content = None if args.no_markdown else _render_markdown(payload)
    sb = _sb()

    raw_doc_type = (
        args.doc_type_label
        if args.doc_type_label is not None
        else str(payload.get("doc_type") or "")
    )
    doc_type_col = raw_doc_type.strip() if raw_doc_type and raw_doc_type.strip() else None

    row = {
        "date": date_str,
        "title": args.title,
        "doc_type": doc_type_col,
        "phase": None,
        "category": args.category,
        "segment": str(payload.get("doc_type") or ""),
        "sector": None,
        "run_type": payload.get("run_type"),
        "document_key": args.document_key,
        "payload": payload,
        "content": content,
    }

    sb.table("documents").upsert(row, on_conflict="date,document_key").execute()
    print(f"✅ published documents:{date_str}/{args.document_key}")
    return 0


if __name__ == "__main__":
    sys.exit(main())

