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

The printed summary's ``d1_notes`` is a ``SELECT COUNT(*)`` against the table
itself, read back after the FTS rebuild -- unlike ``notes``/``written``, which are
both source-side (rows this run read and sent), ``d1_notes`` reflects what is
actually in D1, including any row a prior run wrote that this run's source no
longer has (a deleted note, or a re-chunk that renamed a segment's ``vault_path``).
This script never deletes such orphans -- it only surfaces the discrepancy for an
operator to act on.

Apply::

    D1_ACCOUNT_ID=… D1_API_TOKEN=… \\
      python3 scripts/d1_sync.py --prefix clients/digithings --database <id> --vault /data/vault

One-time backfill (see the #2239 runbook for the expected counts to verify against).
``--from-supabase`` needs the ``digivault[supabase]`` extra installed and
``CORE_SUPABASE_URL`` plus a key (``CORE_SUPABASE_ANON_KEY`` or
``CORE_SUPABASE_SERVICE_KEY``) set, on top of the ``D1_ACCOUNT_ID``/``D1_API_TOKEN``
every mode needs::

    D1_ACCOUNT_ID=… D1_API_TOKEN=… CORE_SUPABASE_URL=… CORE_SUPABASE_SERVICE_KEY=… \\
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
from digivault.supabase_store import SupabaseStoreError
from digivault.vault import _normalize_tags

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
    "INSERT INTO notes "
    "(vault_path, title, note_type, summary, body, frontmatter, tags, wikilinks, "
    "parent_doc, segment_index, updated_at) VALUES "
)

#: `vault_path` is a TEXT PRIMARY KEY, not a rowid alias, so `INSERT OR REPLACE`
#: (SQLite's REPLACE conflict resolution -- D1 is SQLite) deletes and reinserts the
#: conflicting row, assigning it a *new* rowid. `D1Store`'s `_SEARCH_SQL` joins
#: `n.rowid = notes_fts.rowid`, and external-content FTS5 does not self-populate on
#: INSERT/UPDATE -- only the `rebuild` in `REBUILD_FTS_SQL` refreshes it. Between a
#: rowid-churning re-sync and its rebuild call, or whenever that rebuild call fails
#: outright, the FTS index is left mapping old rowids to nothing and search returns
#: zero rows for every note the last successful rebuild indexed -- not just the ones
#: this run touched (#2239 review, Important I1). `ON CONFLICT(vault_path) DO
#: UPDATE` updates the conflicting row in place instead of deleting and reinserting
#: it, so its rowid survives the upsert -- the FTS-to-notes rowid mapping stays
#: valid even if the rebuild that would refresh its *text* fails, worst case ranking
#: a note on its previous content instead of returning nothing for it at all.
UPSERT_CONFLICT_SUFFIX = (
    " ON CONFLICT(vault_path) DO UPDATE SET "
    "title=excluded.title, note_type=excluded.note_type, summary=excluded.summary, "
    "body=excluded.body, frontmatter=excluded.frontmatter, tags=excluded.tags, "
    "wikilinks=excluded.wikilinks, parent_doc=excluded.parent_doc, "
    "segment_index=excluded.segment_index, updated_at=excluded.updated_at"
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
    sql = UPSERT_PREFIX + placeholders + UPSERT_CONFLICT_SUFFIX
    payload = {"sql": sql, "params": params}
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
    """Refuse a note that could never be published, however it's batched.

    Checks both of D1's per-row hard caps up front, before any D1 call (same as the
    duplicate-path guard above): the 2,000,000-byte row cap (``_row_bytes``, the
    row's own serialized params) and the 100,000-byte statement cap as it would
    apply if this row ever ends up alone in a batch (``_statement_bytes`` on a
    solo-row batch). ``_split_to_fit`` recursively halves an oversized multi-row
    batch down to single rows, so an outlier row eventually reaches D1 by itself --
    a row between the two caps (comfortably under 2 MB, but over 100 KB once its own
    single-row UPSERT SQL text and JSON envelope are added) used to slip past this
    check *and* ``_split_to_fit``'s single-row base case, reaching D1 as an oversized
    lone statement and failing mid-run with any earlier batches already committed
    (#2239 review, Minor M1) -- exactly the failure this guard exists to prevent.
    """
    for row in rows:
        size = _row_bytes(row)
        if size > MAX_ROW_BYTES:
            raise ValueError(
                f"{row[0]!r} serializes to {size} bytes, exceeding D1's {MAX_ROW_BYTES}-byte "
                "row cap; this note cannot be published as a single row"
            )
        solo_statement_bytes = _statement_bytes([row])
        if solo_statement_bytes > MAX_STATEMENT_BYTES:
            raise ValueError(
                f"{row[0]!r} alone serializes to a {solo_statement_bytes}-byte statement, "
                f"exceeding D1's {MAX_STATEMENT_BYTES}-byte statement cap even sent by "
                "itself; this note cannot be published as a single row"
            )


def _ensure_unique_vault_paths(rows: list[list[Any]]) -> None:
    """Refuse to publish if the source yielded the same ``vault_path`` more than once.

    ``vault_path`` is the notes table's PRIMARY KEY (``d1_schema.sql``), so the
    upsert's ``ON CONFLICT(vault_path) DO UPDATE`` would silently collapse
    duplicates within/across batches (last one wins) and the write loop would still
    report ``written == notes`` -- exactly the duplication
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


def row_params(
    *,
    vault_path: str,
    title: str,
    frontmatter: dict[str, Any],
    body: str,
    note_type: str | None = None,
    summary: str | None = None,
    wikilinks: Sequence[Any] | None = None,
) -> list[Any]:
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

    ``note_type``/``summary``/``wikilinks`` default to the matching frontmatter key
    when omitted (``None``) -- the on-disk vault's shape, where all three are YAML
    frontmatter, not table columns. ``_read_supabase`` passes them explicitly
    instead: in ``architecture_notes`` these three are top-level table columns
    (``scripts/sync_architecture_vault.py``), not frontmatter keys, and defaulting
    to ``frontmatter.get(...)`` there silently dropped all three for every
    backfilled note (#2239 review, Important I2).

    ``tags`` has no such explicit parameter -- unlike its three siblings above, it
    **is** in ``_SUPABASE_BACKFILL_SELECT`` behind ``frontmatter`` (the raw YAML
    round-trips into that JSON blob's own ``tags`` key), so both read paths do land
    on the same underlying value; there is no #2239-I2-style row loss here. But
    that raw value is whatever a hand-edited note's YAML actually contains -- a
    comma/space-separated string (``tags: arch, graph``), a ``#``-prefixed list
    entry, or a proper list -- and ``Vault`` itself never stores ``tags`` un-
    normalised; every other reader goes through ``_normalize_tags``
    (``digivault.vault``). Doing the same here, rather than ``list(...)`` over
    whatever frontmatter happens to hold, avoids silently exploding a string value
    into one row per character (#2239 review, Minor finding).
    """
    segment_index = frontmatter.get("segment_index")
    resolved_note_type = note_type if note_type is not None else str(frontmatter.get("type") or "")
    resolved_summary = summary if summary is not None else str(frontmatter.get("summary") or "")
    resolved_wikilinks = (
        list(wikilinks) if wikilinks is not None else list(frontmatter.get("wikilinks") or [])
    )
    return [
        normalize_vault_path(vault_path),
        title or str(frontmatter.get("title") or ""),
        str(resolved_note_type),
        str(resolved_summary),
        body or "",
        json.dumps(frontmatter, sort_keys=True, default=str),
        json.dumps(list(_normalize_tags(frontmatter.get("tags")))),
        json.dumps(resolved_wikilinks),
        (str(frontmatter["parent_doc"]) if frontmatter.get("parent_doc") else None),
        (int(segment_index) if isinstance(segment_index, int) else None),
        str(frontmatter.get("ingested_at") or ""),
    ]


def _read_vault(vault_root: Path, prefix: str) -> list[list[Any]]:
    """Read every note under ``prefix`` from an on-disk vault directory.

    ``summary``/``wikilinks`` are derived from ``body`` here -- the same way
    ``sync_architecture_vault.py``'s ``build_rows`` derives them for the Supabase
    publisher this read path replaces (``_summary_from_body``; wikilink targets via
    ``digivault.wikilinks.parse_links``, matching ``Vault``'s own outlink computation)
    -- rather than left to ``row_params``'s frontmatter-key fallback. That fallback is
    always empty here: the onboard writer (``scripts/docs_onboard/write_vault_notes.py``)
    never puts either key in frontmatter, so every note synced through the ongoing CI
    publish path (``--vault``, not the one-time ``--from-supabase`` backfill) would
    write empty ``summary``/``wikilinks`` on its first push to ``main`` -- undoing the
    backfill's restored values (#2239 review, Minor finding).
    """
    from digivault.wikilinks import parse_links

    from digivault import frontmatter as fm
    from scripts.sync_architecture_vault import _summary_from_body

    out: list[list[Any]] = []
    for path in sorted(vault_root.rglob("*.md")):
        rel = normalize_vault_path(str(path.relative_to(vault_root)))
        if rel != prefix and not rel.startswith(prefix + "/"):
            continue
        meta, body = fm.split_frontmatter(path.read_text(encoding="utf-8"))
        out.append(
            row_params(
                vault_path=rel,
                title=str(meta.get("title") or ""),
                frontmatter=meta,
                body=body,
                summary=_summary_from_body(body),
                wikilinks=sorted({link.target for link in parse_links(body)}),
            )
        )
    return out


#: Columns this backfill needs beyond ``SupabaseStore``'s ``_SELECT`` (which only
#: carries the four columns on-disk-vault-shaped callers need). In
#: ``architecture_notes``, ``note_type``/``summary``/``wikilinks`` are top-level
#: table columns (``scripts/sync_architecture_vault.py``'s ``build_rows``), not
#: frontmatter keys -- reading through ``SupabaseStore.list_notes``/``NoteRow``
#: (shared with other callers) silently dropped all three for every backfilled note
#: (#2239 review, Important I2). Selected via ``SupabaseStore.list_raw`` -- a select
#: list local to this backfill path -- rather than widening ``NoteRow`` itself,
#: so this one-off need never ripples to ``list_notes``'s other callers.
_SUPABASE_BACKFILL_SELECT = "vault_path,title,frontmatter,body_markdown,note_type,summary,wikilinks"


def _read_supabase(prefix: str) -> list[list[Any]]:
    """Read every note under ``prefix`` from Supabase ``architecture_notes``.

    Only for ``--from-supabase`` (the one-time backfill) -- never used inside the
    container, which only ever reads D1.
    """
    from digivault.supabase_store import SupabaseStore

    rows = SupabaseStore.from_env().list_raw(select=_SUPABASE_BACKFILL_SELECT, path_prefix=prefix)
    return [
        row_params(
            vault_path=str(row.get("vault_path") or ""),
            title=str(row.get("title") or ""),
            frontmatter=dict(row.get("frontmatter") or {}),
            body=str(row.get("body_markdown") or ""),
            note_type=(str(row["note_type"]) if row.get("note_type") is not None else None),
            summary=(str(row["summary"]) if row.get("summary") is not None else None),
            wikilinks=(row.get("wikilinks") if row.get("wikilinks") is not None else None),
        )
        for row in rows
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
        help=(
            "one-time backfill: read architecture_notes instead of a vault directory. "
            "Needs the digivault[supabase] extra installed AND CORE_SUPABASE_URL plus "
            "a key (CORE_SUPABASE_ANON_KEY or CORE_SUPABASE_SERVICE_KEY) set -- on top "
            "of D1_ACCOUNT_ID/D1_API_TOKEN, which every mode needs."
        ),
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

    try:
        rows = (
            _read_supabase(prefix) if args.from_supabase else _read_vault(Path(args.vault), prefix)
        )
    except SupabaseStoreError as exc:
        # `_read_supabase` (--from-supabase only) calls `SupabaseStore.from_env()`,
        # which raises this bare-RuntimeError subclass when CORE_SUPABASE_URL + a key
        # aren't set -- previously unhandled, so this was the first unhandled
        # traceback the imminent cutover would hit: the runbook's credential step
        # exports only D1_ACCOUNT_ID/D1_API_TOKEN, and neither it nor --from-supabase's
        # own help text mentioned Supabase creds were also needed. Every sibling error
        # path in this script (empty-corpus guard above, the D1StoreError arm below)
        # prints `error: ...` and returns 1; this class of failure gets the same
        # clean CLI error instead of a traceback (#2239 review, Important finding;
        # mirrors vectorize_sync.py's D1StoreError handling for the same class).
        print(f"error: {exc}", file=sys.stderr)
        return 1
    if not rows:
        # `Path.rglob` on a missing/empty directory yields nothing rather than
        # raising, and an empty Supabase page under a wrong prefix is
        # indistinguishable from "no matches" -- either way, a typo'd --vault or
        # --prefix used to be a clean exit 0 reporting `written: 0`, a green CI run
        # that published nothing (#2239 review, Important I3). Matches the guard
        # `scripts/sync_onboard_vault.py` already has (lines 60-63) for the same
        # class of mistake on its sibling read path.
        source = "Supabase architecture_notes" if args.from_supabase else args.vault
        print(
            f"error: no notes found under prefix {prefix!r} in {source!r}; refusing to "
            "publish an empty corpus (check --vault/--prefix)",
            file=sys.stderr,
        )
        return 1
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
                sql = UPSERT_PREFIX + placeholders + UPSERT_CONFLICT_SUFFIX
                store.query(sql, params, operation="upsert")
                written += len(safe_batch)
                print(f"  {written}/{len(rows)}", file=sys.stderr)

        store.query(REBUILD_FTS_SQL, [], operation="rebuild_fts")
        # `written` is source-side: rows read and sent this run, never read back
        # from D1 itself. A note deleted from the vault (or renamed by a re-chunk
        # that changes segment slugs -- the #2138 accumulation shape one level down)
        # leaves an orphaned row that `written` can never surface, so the runbook's
        # "halt unless exactly 1279 / 328" check was only ever verifying what was
        # read, not what is actually in D1 (#2239 review, Minor M3). This is a read
        # only -- it does not delete orphans; see the module docstring for what
        # `d1_notes` means and why deletion is a separate, bigger decision.
        count_rows = store.query("SELECT COUNT(*) AS count FROM notes", [], operation="count")
    except D1StoreError as exc:
        print(f"error: {exc}", file=sys.stderr)
        return 1

    d1_notes = (
        int(count_rows[0]["count"]) if count_rows and count_rows[0].get("count") is not None else 0
    )
    print(
        json.dumps({"prefix": prefix, "notes": len(rows), "written": written, "d1_notes": d1_notes})
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
