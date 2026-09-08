#!/usr/bin/env python3
"""Inventory legacy ``documents`` into research-state manifests (#2870 / WP12.4).

Writes only ``LegacyDocumentRef`` rows (``legacy_manifest_only``, ``known_at=None``).
Never fabricates evidence, beliefs, expected events, patches, or known times.
Strict readers exclude the inventory (WP12.2).

Default mode is dry-run (count only). Pass ``--apply`` to append via the
in-memory :class:`~digiquant.dashboard.research_retrieval.store.ResearchStateStore`
(SQL IO adapter later — does not INSERT ``olympus_research_legacy_refs`` yet).

Usage:
  python digiquant/scripts/research/backfill_research_state.py
  python digiquant/scripts/research/backfill_research_state.py --apply
  python digiquant/scripts/research/backfill_research_state.py --documents-json path.json
  python digiquant/scripts/research/backfill_research_state.py --supabase --apply

Environment (``--supabase``): CORE_SUPABASE_URL / CORE_SUPABASE_SERVICE_KEY
(or legacy SUPABASE_* names).
"""

from __future__ import annotations

import argparse
import json
import os
import sys
from pathlib import Path
from typing import Any  # score:allow untyped any — scored-lint: heterogeneous dict / client shapes

try:
    from dotenv import load_dotenv  # type: ignore[import-not-found]

    load_dotenv(Path(__file__).parent.parent / "config" / "supabase.env")
    load_dotenv()
except ImportError:
    pass


def _ensure_src_path() -> None:
    root = Path(__file__).resolve().parents[3]
    src = root / "digiquant" / "src"
    if str(src) not in sys.path:
        sys.path.insert(0, str(src))


_ensure_src_path()
from digiquant.dashboard.tenancy import eq_house_workspace  # noqa: E402


def _sb():
    try:
        from supabase import create_client  # type: ignore[import-not-found]
    except ImportError as exc:
        raise RuntimeError("pip install supabase") from exc
    url = os.environ.get("CORE_SUPABASE_URL", os.environ.get("SUPABASE_URL"))
    key = os.environ.get("CORE_SUPABASE_SERVICE_KEY", os.environ.get("SUPABASE_SERVICE_ROLE_KEY"))
    if not url or not key:
        raise RuntimeError("SUPABASE_URL and SUPABASE_SERVICE_ROLE_KEY required")
    return create_client(url, key)


def _load_sources_from_json(path: Path) -> list[Any]:
    from digiquant.dashboard.research_retrieval.legacy_backfill import LegacySourceDocument

    raw = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(raw, list):
        raise ValueError("--documents-json must be a JSON array of source objects")
    return [LegacySourceDocument.model_validate(item) for item in raw]


def _load_sources_from_supabase(*, page_size: int = 1000, client: Any | None = None) -> list[Any]:
    """House ``documents`` pages. Overlay rows must not seed the house inventory."""
    from digiquant.dashboard.research_retrieval.legacy_backfill import LegacySourceDocument

    sb = client if client is not None else _sb()
    sources: list[LegacySourceDocument] = []
    offset = 0
    while True:
        resp = (
            eq_house_workspace(sb.table("documents").select("date,document_key,payload"))
            .order("date")
            .order("document_key")
            .range(offset, offset + page_size - 1)
            .execute()
        )
        rows = getattr(resp, "data", None) or []
        if not rows:
            break
        for row in rows:
            sources.append(
                LegacySourceDocument(
                    document_key=str(row.get("document_key") or ""),
                    as_of_date=str(row.get("date") or "")[:10],
                    source_table="documents",
                    payload=row.get("payload"),
                )
            )
        if len(rows) < page_size:
            break
        offset += page_size
    return sources


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        description=(
            "Backfill non-fabricating legacy research-state manifests "
            "(inventory only; default dry-run)."
        )
    )
    parser.add_argument(
        "--apply",
        action="store_true",
        help=(
            "Append LegacyDocumentRef rows to in-memory ResearchStateStore "
            "(default: dry-run; not durable SQL)."
        ),
    )
    parser.add_argument(
        "--documents-json",
        type=Path,
        help="JSON array of {document_key, as_of_date, payload[, source_table]} sources.",
    )
    parser.add_argument(
        "--supabase",
        action="store_true",
        help="Load source rows from public.documents (paginated).",
    )
    args = parser.parse_args(argv)

    if args.documents_json is not None and args.supabase:
        print("error: choose at most one of --documents-json or --supabase", file=sys.stderr)
        return 2

    _ensure_src_path()
    from digiquant.dashboard.research_retrieval.legacy_backfill import backfill_legacy_manifests
    from digiquant.dashboard.research_retrieval.store import ResearchStateStore

    if args.documents_json is not None:
        sources = _load_sources_from_json(args.documents_json)
    elif args.supabase:
        try:
            sources = _load_sources_from_supabase()
        except RuntimeError as exc:
            print(f"error: {exc}", file=sys.stderr)
            return 2
    else:
        sources = []
        print(
            "note: no --documents-json / --supabase; counting empty source set",
            file=sys.stderr,
        )

    store = ResearchStateStore()
    if args.apply:
        print(
            "warning: ResearchStateStore is in-process only (SQL IO adapter later); "
            "--apply does not INSERT into olympus_research_legacy_refs",
            file=sys.stderr,
        )
    counts = backfill_legacy_manifests(sources, store, apply=bool(args.apply))
    mode = "apply" if args.apply else "dry-run"
    print(
        f"[{mode}] source={counts.source} inserted={counts.inserted} "
        f"skipped={counts.skipped} unverifiable={counts.unverifiable}"
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
