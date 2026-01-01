#!/usr/bin/env python3
"""Seed / upsert a filesystem markdown vault into Supabase ``public.knowledge_notes``.

Dogfoods digivault (parse) + digibase[supabase] (idempotent upsert). Rows are
namespaced by the ``vault`` column so one table can hold multiple corpora
(#1142). Default namespace is ``finance`` (the digiquant theory KB).

Usage
-----
Dry-run (no DB)::

    PYTHONPATH=. uv run python scripts/seed_knowledge_vault.py --dry-run

Seed the finance vault from ``docs/knowledge`` (default paths)::

    PYTHONPATH=. uv run python scripts/seed_knowledge_vault.py

Seed a different namespace / directory::

    PYTHONPATH=. uv run python scripts/seed_knowledge_vault.py \\
        --vault product --vault-dir docs/product-suite

Credentials resolve ``CORE_SUPABASE_URL`` / ``CORE_SUPABASE_SERVICE_KEY``
(ADR-0022), falling back to ``SUPABASE_URL`` / ``SUPABASE_SERVICE_ROLE_KEY``.
Never hardcoded, never logged. Upsert conflict target is ``(vault, vault_path)``
(migration 118).
"""

from __future__ import annotations

import argparse
import json
import sys
from datetime import datetime, timezone
from pathlib import Path
from typing import Any  # score:allow untyped any — frontmatter/row values are arbitrary YAML/JSON

from digivault import Vault, split_frontmatter

DEFAULT_VAULT_DIR = "docs/knowledge"
DEFAULT_TABLE = "knowledge_notes"
DEFAULT_VAULT = "finance"


def _jsonable(value: Any) -> Any:
    """Round-trip through JSON so YAML dates/tuples become JSON-safe scalars."""
    return json.loads(json.dumps(value, default=str))


def _summary_from_body(body: str) -> str:
    """First blockquote line, else first non-heading prose line."""
    for line in body.splitlines():
        stripped = line.strip()
        if stripped.startswith(">"):
            return stripped.lstrip(">").strip()
    for line in body.splitlines():
        stripped = line.strip()
        if stripped and not stripped.startswith("#"):
            return stripped
    return ""


def _normalize_relevance(value: Any) -> list[str]:
    """Coerce frontmatter relevance to a string list (never character-split a str)."""
    if value is None:
        return []
    if isinstance(value, str):
        stripped = value.strip()
        return [stripped] if stripped else []
    if isinstance(value, (list, tuple)):
        return [str(v).strip() for v in value if str(v).strip()]
    return []


def build_rows(vault_dir: str, *, vault: str) -> list[dict[str, Any]]:
    """Parse the vault with digivault and map each note to a knowledge_notes row."""
    index = Vault(vault_dir)
    rows: list[dict[str, Any]] = []
    for note in index.list_notes():
        frontmatter, body = split_frontmatter(index.read_text(note.name))
        vault_path = note.rel_path[:-3] if note.rel_path.endswith(".md") else note.rel_path
        rows.append(
            {
                "vault": vault,
                "slug": note.name,
                "vault_path": vault_path,
                "title": note.title or frontmatter.get("title") or note.name,
                "note_type": str(
                    frontmatter.get("type", frontmatter.get("note_type", "reference"))
                ),
                "status": str(frontmatter.get("status", "stub")),
                "tags": list(note.tags),
                "relevance": [str(r) for r in _normalize_relevance(frontmatter.get("relevance"))],
                "summary": str(frontmatter.get("summary") or _summary_from_body(body)),
                "body_markdown": body,
                "frontmatter": _jsonable(frontmatter),
                "sources": _jsonable(frontmatter.get("sources") or []),
                "wikilinks": sorted({link.target for link in note.outlinks}),
            }
        )
    return rows


def _connector():  # type: ignore[no-untyped-def]
    """Build a digibase SupabaseConnector, preferring the ADR-0022 CORE_* names."""
    from digibase.connectors.supabase import (  # deferred: optional extra
        SupabaseConnector,
        SupabaseNotConfiguredError,
    )

    candidates = (
        ("CORE_SUPABASE_URL", "CORE_SUPABASE_SERVICE_KEY"),
        ("SUPABASE_URL", "SUPABASE_SERVICE_ROLE_KEY"),
    )
    for url_var, key_var in candidates:
        try:
            return SupabaseConnector.from_env(url_var=url_var, key_var=key_var)
        except SupabaseNotConfiguredError:
            continue
    raise SystemExit(
        "No Supabase credentials found. Set CORE_SUPABASE_URL + CORE_SUPABASE_SERVICE_KEY "
        "(or SUPABASE_URL + SUPABASE_SERVICE_ROLE_KEY)."
    )


def _print_dry_run(rows: list[dict[str, Any]]) -> None:
    preview = [
        {
            "vault": r["vault"],
            "vault_path": r["vault_path"],
            "title": r["title"],
            "note_type": r["note_type"],
            "status": r["status"],
            "tags": r["tags"],
            "wikilinks": r["wikilinks"],
            "body_chars": len(r["body_markdown"]),
        }
        for r in rows
    ]
    print(json.dumps(preview, indent=2))


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        description="Seed a markdown vault → Supabase knowledge_notes (namespaced)."
    )
    parser.add_argument(
        "--vault",
        default=DEFAULT_VAULT,
        help=f"Vault namespace column value (default: {DEFAULT_VAULT}).",
    )
    parser.add_argument(
        "--vault-dir",
        default=DEFAULT_VAULT_DIR,
        help=f"Filesystem vault root (default: {DEFAULT_VAULT_DIR}).",
    )
    parser.add_argument("--table", default=DEFAULT_TABLE, help="Target table.")
    parser.add_argument(
        "--dry-run", action="store_true", help="Parse and print rows; no DB connection."
    )
    args = parser.parse_args(argv)

    vault_ns = args.vault.strip()
    if not vault_ns:
        print("--vault must be a non-empty namespace", file=sys.stderr)
        return 2
    if not Path(args.vault_dir).is_dir():
        print(f"Vault directory not found: {args.vault_dir}", file=sys.stderr)
        return 1

    rows = build_rows(args.vault_dir, vault=vault_ns)
    if not rows:
        print(f"No notes found in {args.vault_dir}", file=sys.stderr)
        return 1

    if args.dry_run:
        _print_dry_run(rows)
        print(
            f"\n[dry-run] {len(rows)} notes parsed from {args.vault_dir} (vault={vault_ns!r})",
            file=sys.stderr,
        )
        return 0

    timestamp = datetime.now(timezone.utc).isoformat()
    for row in rows:
        row["updated_at"] = timestamp

    # Composite unique from migration 118 — idempotent re-runs update in place.
    result = _connector().upsert(args.table, rows, on_conflict="vault,vault_path")
    if not result.success:
        print(f"Upsert failed: {result.error}", file=sys.stderr)
        return 1
    print(f"Seeded {result.rows} notes → {args.table} (vault={vault_ns!r})")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
