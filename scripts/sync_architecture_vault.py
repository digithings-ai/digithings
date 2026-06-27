#!/usr/bin/env python3
"""Sync the DigiVault-managed ``docs/vision`` vault → Supabase ``public.architecture_notes``.

Dogfoods two DigiThings modules:

* **digivault** — parses the Obsidian vault (YAML frontmatter, body, ``[[wikilinks]]``)
  via the core ``Vault`` index. It is the single source of truth for note structure.
* **digibase[supabase]** — idempotent ``upsert`` keyed on ``vault_path`` (``on_conflict``).

The repo docs stay the source of truth; this publishes them to Supabase so the
digithings.ai docs chat can read + full-text-search them (migration 048).

Usage
-----
Dry-run (no DB, no credentials — verifies the parse/mapping)::

    PYTHONPATH=digivault/src:digibase/src python3 -P scripts/sync_architecture_vault.py --dry-run

Real sync (CI / operator; needs service-role credentials in the environment)::

    python3 scripts/sync_architecture_vault.py

Credentials resolve ``CORE_SUPABASE_URL`` / ``CORE_SUPABASE_SERVICE_KEY`` (ADR-0022),
falling back to ``SUPABASE_URL`` / ``SUPABASE_SERVICE_ROLE_KEY``. The service key is read
from the environment only — never hardcoded, never logged.
"""

from __future__ import annotations

import argparse
import json
import sys
from datetime import datetime, timezone
from typing import Any

from digivault import Vault, split_frontmatter

DEFAULT_VAULT = "docs/vision"
DEFAULT_TABLE = "architecture_notes"


def _jsonable(value: Any) -> Any:
    """Round-trip through JSON so YAML dates/tuples become JSON-safe scalars."""
    return json.loads(json.dumps(value, default=str))


def _summary_from_body(body: str) -> str:
    """The note's tagline — the first Markdown blockquote line under the H1."""
    for line in body.splitlines():
        stripped = line.strip()
        if stripped.startswith(">"):
            return stripped.lstrip(">").strip()
    for line in body.splitlines():  # fallback: first non-heading, non-empty line
        stripped = line.strip()
        if stripped and not stripped.startswith("#"):
            return stripped
    return ""


def build_rows(vault_dir: str) -> list[dict[str, Any]]:
    """Parse the vault with DigiVault and map each note to an architecture_notes row."""
    vault = Vault(vault_dir)
    rows: list[dict[str, Any]] = []
    for note in vault.list_notes():
        frontmatter, body = split_frontmatter(vault.read_text(note.name))
        vault_path = note.rel_path[:-3] if note.rel_path.endswith(".md") else note.rel_path
        rows.append(
            {
                "slug": note.name,
                "vault_path": vault_path,
                "title": note.title or frontmatter.get("title") or note.name,
                "note_type": str(frontmatter.get("type", "reference")),
                "status": str(frontmatter.get("status", "stub")),
                "tags": list(note.tags),
                "relevance": [str(r) for r in (frontmatter.get("relevance") or [])],
                "summary": _summary_from_body(body),
                "body_markdown": body,
                "frontmatter": _jsonable(frontmatter),
                "sources": _jsonable(frontmatter.get("sources") or []),
                "wikilinks": sorted({link.target for link in note.outlinks}),
            }
        )
    return rows


def _connector():  # type: ignore[no-untyped-def]
    """Build a digibase SupabaseConnector, preferring the ADR-0022 CORE_* names."""
    from digibase.connectors.supabase import (  # noqa: PLC0415 (deferred: optional extra)
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
    """Compact, body-free view so the mapping is easy to eyeball."""
    preview = [
        {
            "vault_path": r["vault_path"],
            "title": r["title"],
            "note_type": r["note_type"],
            "status": r["status"],
            "tags": r["tags"],
            "relevance": r["relevance"],
            "summary": r["summary"],
            "wikilinks": r["wikilinks"],
            "body_chars": len(r["body_markdown"]),
        }
        for r in rows
    ]
    print(json.dumps(preview, indent=2))


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Sync docs/vision vault → Supabase.")
    parser.add_argument("--vault", default=DEFAULT_VAULT, help="Vault root (default: docs/vision).")
    parser.add_argument("--table", default=DEFAULT_TABLE, help="Target table.")
    parser.add_argument(
        "--dry-run", action="store_true", help="Parse and print rows; no DB connection."
    )
    args = parser.parse_args(argv)

    rows = build_rows(args.vault)
    if not rows:
        print(f"No notes found in {args.vault}", file=sys.stderr)
        return 1

    if args.dry_run:
        _print_dry_run(rows)
        print(f"\n[dry-run] {len(rows)} notes parsed from {args.vault}", file=sys.stderr)
        return 0

    timestamp = datetime.now(timezone.utc).isoformat()
    for row in rows:
        row["updated_at"] = timestamp

    result = _connector().upsert(args.table, rows, on_conflict="vault_path")
    if not result.success:
        print(f"Upsert failed: {result.error}", file=sys.stderr)
        return 1
    print(f"Synced {result.rows} notes → {args.table}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
