#!/usr/bin/env python3
"""Sync an onboard digivault directory → Supabase ``public.architecture_notes``.

Stage 4 of the digithings dogfood cutover. Reuses the same row mapping as
``sync_architecture_vault.py`` but allows operator vault paths (not only
``docs/*``) while still refusing confidential ``projects/`` trees.

Dry-run needs no credentials::

    PYTHONPATH=digivault/src:digibase/src python3 -P scripts/sync_onboard_vault.py \\
      --vault /tmp/digithings-onboard-vault --dry-run

Apply (service role; never log secrets)::

    CORE_SUPABASE_URL=… CORE_SUPABASE_SERVICE_KEY=… \\
      python3 scripts/sync_onboard_vault.py --vault /data/vault
"""

from __future__ import annotations

import argparse
import sys
from datetime import datetime, timezone
from pathlib import Path

from scripts.sync_architecture_vault import (  # reuse mapping + connector
    DEFAULT_TABLE,
    _connector,
    _print_dry_run,
    build_rows,
)


def _prune_stale_children(
    connector: object, table: str, rows: list[dict[str, object]]
) -> list[str]:
    """Delete remote children absent from the authoritative local rows, per parent directory."""
    hubs = [
        row
        for row in rows
        if isinstance(row.get("slug"), str)
        and isinstance(row.get("vault_path"), str)
        and (
            not isinstance(row.get("frontmatter"), dict) or not row["frontmatter"].get("parent_doc")
        )
    ]
    deleted: list[str] = []
    for hub in hubs:
        parent = str(hub["slug"])
        hub_path = str(hub["vault_path"])
        directory = hub_path.rpartition("/")[0]
        expected = {
            str(row["vault_path"])
            for row in rows
            if isinstance(row.get("frontmatter"), dict)
            and row["frontmatter"].get("parent_doc") == parent
            and str(row.get("vault_path", "")).rpartition("/")[0] == directory
        }
        result = connector.select(  # type: ignore[attr-defined]
            table, columns="vault_path", eq={"frontmatter->>parent_doc": parent}
        )
        if not result.success:
            raise RuntimeError(f"Failed to list remote children for {parent!r}: {result.error}")
        stale = sorted(
            str(row["vault_path"])
            for row in result.rows
            if isinstance(row.get("vault_path"), str)
            and str(row["vault_path"]).rpartition("/")[0] == directory
            and str(row["vault_path"]) not in expected
        )
        if not stale:
            continue
        delete_result = connector.delete(table, in_={"vault_path": stale})  # type: ignore[attr-defined]
        if not delete_result.success:
            raise RuntimeError(
                f"Failed to prune remote children for {parent!r}: {delete_result.error}"
            )
        deleted.extend(stale)
    return deleted


def _assert_not_confidential(vault_dir: str) -> None:
    """Refuse confidential ``projects/`` trees; allow operator /tmp and docs vaults."""
    parts = Path(vault_dir).resolve().parts
    if "projects" in parts:
        raise SystemExit(
            f"refusing to sync {vault_dir!r}: confidential projects/ paths must not "
            "reach the anon-readable architecture_notes table."
        )


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--vault",
        required=True,
        help="Onboard vault root (local DIGIVAULT_ROOT or exported tree).",
    )
    parser.add_argument("--table", default=DEFAULT_TABLE, help="Target table.")
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="Parse and print rows; no DB connection / no credentials required.",
    )
    args = parser.parse_args(argv)

    _assert_not_confidential(args.vault)
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
        # Prefer onboard page_class / type from frontmatter when present
        fm = row.get("frontmatter") or {}
        if isinstance(fm, dict) and fm.get("page_class") == "openapi":
            row["note_type"] = str(fm.get("type") or "api_reference")

    connector = _connector()
    result = connector.upsert(args.table, rows, on_conflict="vault_path")
    if not result.success:
        print(f"Upsert failed: {result.error}", file=sys.stderr)
        return 1
    try:
        deleted = _prune_stale_children(connector, args.table, rows)
    except RuntimeError as exc:
        print(str(exc), file=sys.stderr)
        return 1
    print(f"Synced {result.rows} notes → {args.table}; pruned {len(deleted)} stale children")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
