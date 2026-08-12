#!/usr/bin/env python3
"""Publish a digivault corpus into a Cloudflare D1 database.

Reads notes from an onboard vault directory (the normal path, ``--vault``) or, with
``--from-supabase``, from ``architecture_notes`` for the one-time backfill of the
existing corpus. Writes are batched under D1's 100-bound-parameter cap and its
100,000-byte statement / 2,000,000-byte row caps. Run by an operator or CI, never
inside the Cloudflare Container -- production only ever reads (``digivault.d1_store``).

``--dry-run`` still reads and counts -- that's the only way to get an accurate
preview -- but needs no ``D1_ACCOUNT_ID``/``D1_API_TOKEN`` and makes zero D1 calls:
no schema init, no upsert, no FTS rebuild.

Apply::

    D1_ACCOUNT_ID=… D1_API_TOKEN=… \\
      python3 scripts/d1_sync.py --prefix clients/digithings --database <id> --vault /data/vault

One-time backfill (see the #2239 runbook for the expected counts to verify against)::

    D1_ACCOUNT_ID=… D1_API_TOKEN=… \\
      python3 scripts/d1_sync.py --prefix clients/digithings --database <id> --init --from-supabase
"""

from __future__ import annotations

import argparse
import json
import os
import sys
from collections.abc import Iterator, Sequence
from pathlib import Path
from typing import Any  # score:allow untyped any -- row params are heterogeneous SQL values

from digivault.d1_errors import D1StoreError
from digivault.d1_store import D1Store, normalize_vault_path, resolve_path_prefix

#: notes table column count -- keep in step with digivault/src/digivault/d1_schema.sql
PARAMS_PER_ROW = 11

#: D1 caps bound parameters at 100 per query. Task 1 deleted this same constant as
#: dead code because no write path referenced it yet, with a commitment to reintroduce
#: it in whichever task built the write path -- this script is that write path.
MAX_BOUND_PARAMS = 100

#: D1's other two hard caps (Cloudflare docs): a statement's serialized SQL+params
#: text, and one row's serialized size. `chunk_statements`'s param cap keeps batches
#: small in the common case (page-sized chunk bodies, verified <=2000 chars against
#: the live content-aware-chunking corpus), but nothing else enforces a byte ceiling
#: -- an outlier note (a hub note listing many children, a mis-chunked oversized page)
#: could still push a batch over either cap.
MAX_STATEMENT_BYTES = 100_000
MAX_ROW_BYTES = 2_000_000

UPSERT_PREFIX = (
    "INSERT OR REPLACE INTO notes "
    "(vault_path, title, note_type, summary, body, frontmatter, tags, wikilinks, "
    "parent_doc, segment_index, updated_at) VALUES "
)

#: External-content FTS5 (`content='notes'`) does not self-populate on INSERT/UPDATE
#: to the content table -- 'rebuild' is the canonical full resync, and it is the only
#: thing that makes a fresh D1Store.search() call return anything after a sync.
REBUILD_FTS_SQL = "INSERT INTO notes_fts(notes_fts) VALUES('rebuild')"


def chunk_statements(
    rows: Sequence[Any], *, params_per_row: int, max_params: int = MAX_BOUND_PARAMS
) -> Iterator[list[Any]]:
    """Split rows so no statement exceeds D1's bound-parameter cap.

    Batch size is derived from ``params_per_row``, never hardcoded -- a later column
    added to ``notes`` (and to ``UPSERT_PREFIX``) shrinks the batch automatically
    instead of silently starting to fail against the live 100-param cap.
    """
    if params_per_row <= 0:
        raise ValueError(f"params_per_row must be positive, got {params_per_row}")
    per_batch = max(1, max_params // params_per_row)
    for start in range(0, len(rows), per_batch):
        yield list(rows[start : start + per_batch])


def _row_bytes(row: Sequence[Any]) -> int:
    """Serialized byte size of one row's params -- D1's row cap is on this shape."""
    return len(json.dumps(row).encode("utf-8"))


def _statement_bytes(batch: Sequence[Sequence[Any]]) -> int:
    """Serialized ``{sql, params}`` byte size D1 would actually receive for ``batch``."""
    placeholders = ", ".join(["(" + ", ".join(["?"] * PARAMS_PER_ROW) + ")"] * len(batch))
    params = [value for row in batch for value in row]
    payload = {"sql": UPSERT_PREFIX + placeholders, "params": params}
    return len(json.dumps(payload).encode("utf-8"))


def _split_to_fit(
    batch: list[list[Any]], *, max_bytes: int = MAX_STATEMENT_BYTES
) -> Iterator[list[list[Any]]]:
    """Halve ``batch`` until its serialized upsert statement fits under ``max_bytes``.

    The common case (a batch of page-sized chunk bodies) already fits and is yielded
    unchanged after one size check. Splitting an over-cap batch here, rather than
    sending it straight to D1, turns a cryptic mid-run API failure into smaller,
    still-successful writes.
    """
    if len(batch) <= 1 or _statement_bytes(batch) <= max_bytes:
        yield batch
        return
    mid = len(batch) // 2
    yield from _split_to_fit(batch[:mid], max_bytes=max_bytes)
    yield from _split_to_fit(batch[mid:], max_bytes=max_bytes)


def _assert_rows_within_byte_cap(rows: list[list[Any]]) -> None:
    """Refuse a single note that could never fit D1's row cap, however it's batched."""
    for row in rows:
        size = _row_bytes(row)
        if size > MAX_ROW_BYTES:
            raise ValueError(
                f"{row[0]!r} serializes to {size} bytes, exceeding D1's {MAX_ROW_BYTES}-byte "
                "row cap; this note cannot be published as a single row"
            )


def _ensure_unique_vault_paths(rows: list[list[Any]]) -> None:
    """Refuse to publish if the source yielded the same ``vault_path`` more than once.

    ``vault_path`` is the notes table's PRIMARY KEY (``d1_schema.sql``), so
    ``INSERT OR REPLACE`` would silently collapse duplicates within/across batches and
    the write loop would still report ``written == notes`` -- exactly the duplication
    class of bug #2138 (rereading the same source content and counting it as new).
    Catching it here means the run aborts before any D1 call, not after a count an
    operator has to notice differs from the runbook's expected 1279 / 328.
    """
    seen: dict[str, int] = {}
    for row in rows:
        seen[row[0]] = seen.get(row[0], 0) + 1
    dupes = sorted(path for path, count in seen.items() if count > 1)
    if dupes:
        raise ValueError(
            f"{len(dupes)} duplicate vault_path value(s) among {len(rows)} rows read "
            f"(e.g. {dupes[:5]!r}); refusing to publish -- see #2138"
        )


def row_params(*, vault_path: str, title: str, frontmatter: dict[str, Any], body: str) -> list[Any]:
    """Flatten one note into positional params matching ``UPSERT_PREFIX``'s column order.

    ``vault_path`` is normalised here (no ``.md``) so every write lands canonical:
    ``D1Store.get_note`` normalises the *lookup* path (Task 1), so a stored
    ``.md``-suffixed path would 404 on every ``digivault_get_note`` call while search
    kept working -- a confusing half-broken state.

    ``json.dumps(frontmatter, ..., default=str)`` is defensive: a hand-edited note
    with an unquoted YAML date (``date: 2026-08-01``) parses to a ``datetime.date``
    via PyYAML's implicit resolver, which plain ``json.dumps`` cannot serialize --
    ``default=str`` degrades that one field to a string instead of failing the whole
    batch over one non-conforming note.
    """
    segment_index = frontmatter.get("segment_index")
    return [
        normalize_vault_path(vault_path),
        title or str(frontmatter.get("title") or ""),
        str(frontmatter.get("type") or ""),
        str(frontmatter.get("summary") or ""),
        body or "",
        json.dumps(frontmatter, sort_keys=True, default=str),
        json.dumps(list(frontmatter.get("tags") or [])),
        json.dumps(list(frontmatter.get("wikilinks") or [])),
        (str(frontmatter["parent_doc"]) if frontmatter.get("parent_doc") else None),
        (int(segment_index) if isinstance(segment_index, int) else None),
        str(frontmatter.get("ingested_at") or ""),
    ]


def _read_vault(vault_root: Path, prefix: str) -> list[list[Any]]:
    """Read every note under ``prefix`` from an on-disk vault directory."""
    from digivault import frontmatter as fm

    out: list[list[Any]] = []
    for path in sorted(vault_root.rglob("*.md")):
        rel = normalize_vault_path(str(path.relative_to(vault_root)))
        if rel != prefix and not rel.startswith(prefix + "/"):
            continue
        meta, body = fm.split_frontmatter(path.read_text(encoding="utf-8"))
        out.append(
            row_params(
                vault_path=rel, title=str(meta.get("title") or ""), frontmatter=meta, body=body
            )
        )
    return out


def _read_supabase(prefix: str) -> list[list[Any]]:
    """Read every note under ``prefix`` from Supabase ``architecture_notes``.

    Only for ``--from-supabase`` (the one-time backfill) -- never used inside the
    container, which only ever reads D1.
    """
    from digivault.supabase_store import SupabaseStore

    notes = SupabaseStore.from_env().list_notes(path_prefix=prefix)
    return [
        row_params(
            vault_path=n.vault_path,
            title=n.title or "",
            frontmatter=dict(n.frontmatter),
            body=n.body_markdown,
        )
        for n in notes
    ]


def _apply_schema(store: D1Store) -> None:
    """Apply ``d1_schema.sql``, one statement per D1 call (D1 rejects multi-statement SQL)."""
    schema_path = Path(__file__).resolve().parent.parent / "digivault/src/digivault/d1_schema.sql"
    schema = schema_path.read_text(encoding="utf-8")
    for statement in [s.strip() for s in schema.split(";") if s.strip()]:
        store.query(statement, [], operation="init")


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--prefix", required=True, help="vault_path prefix, e.g. clients/digithings"
    )
    parser.add_argument(
        "--database",
        required=True,
        help=(
            "D1 database id for this corpus. MUST be the id mapped to --prefix in "
            "D1_DATABASE_MAP (see frontend/digithings-stack-cloudflare/wrangler.toml); "
            "a mismatch means digivault reads a different corpus than this wrote."
        ),
    )
    parser.add_argument("--vault", help="onboard vault root to publish from")
    parser.add_argument(
        "--from-supabase",
        action="store_true",
        help="one-time backfill: read architecture_notes instead of a vault directory",
    )
    parser.add_argument("--init", action="store_true", help="apply d1_schema.sql first")
    parser.add_argument(
        "--dry-run", action="store_true", help="read and count; write nothing, need no credentials"
    )
    args = parser.parse_args(argv)

    if args.from_supabase and args.vault:
        parser.error("provide only one of --vault or --from-supabase, not both")
    if not args.from_supabase and not args.vault:
        parser.error("one of --vault or --from-supabase is required")

    try:
        prefix = resolve_path_prefix(args.prefix)
    except ValueError as exc:
        print(f"error: {exc}", file=sys.stderr)
        return 1

    rows = _read_supabase(prefix) if args.from_supabase else _read_vault(Path(args.vault), prefix)
    try:
        _ensure_unique_vault_paths(rows)
        _assert_rows_within_byte_cap(rows)
    except ValueError as exc:
        print(f"error: {exc}", file=sys.stderr)
        return 1

    print(f"{len(rows)} notes under {prefix!r}", file=sys.stderr)
    if args.dry_run:
        print(json.dumps({"prefix": prefix, "notes": len(rows), "written": 0}))
        return 0

    account_id = os.environ.get("D1_ACCOUNT_ID", "").strip()
    api_token = os.environ.get("D1_API_TOKEN", "").strip()
    if not account_id or not api_token:
        print("error: D1_ACCOUNT_ID and D1_API_TOKEN are required", file=sys.stderr)
        return 1
    store = D1Store(args.database, account_id=account_id, api_token=api_token)

    try:
        if args.init:
            _apply_schema(store)
            print("schema applied", file=sys.stderr)

        written = 0
        for batch in chunk_statements(rows, params_per_row=PARAMS_PER_ROW):
            for safe_batch in _split_to_fit(batch):
                placeholders = ", ".join(
                    ["(" + ", ".join(["?"] * PARAMS_PER_ROW) + ")"] * len(safe_batch)
                )
                params = [value for row in safe_batch for value in row]
                store.query(UPSERT_PREFIX + placeholders, params, operation="upsert")
                written += len(safe_batch)
                print(f"  {written}/{len(rows)}", file=sys.stderr)

        store.query(REBUILD_FTS_SQL, [], operation="rebuild_fts")
    except D1StoreError as exc:
        print(f"error: {exc}", file=sys.stderr)
        return 1

    print(json.dumps({"prefix": prefix, "notes": len(rows), "written": written}))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
