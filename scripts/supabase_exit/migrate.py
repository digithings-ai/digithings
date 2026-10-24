#!/usr/bin/env python3
"""Local-only Supabase dump -> D1/SQLite migration runner (DIG-2893).

Takes Chris's snapshot dump file (ticket 0, DIG-2888) and replays it into a
**local** SQLite file -- the same file ``wrangler d1 execute --local`` uses.
Prints per-table row counts plus SHA-256 checksums for source and target.

Local-only by construction: the dump must be a local file, the target a
local SQLite file, and there is no flag for anything remote -- no D1 REST
client, no Supabase reader, no production binding. ``--dry-run`` parses and
counts without writing anything. Exit non-zero unless every migrated table
verifies.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import sqlite3
import sys
from pathlib import Path

from scripts.supabase_exit.d1_import import import_batches, open_local_db
from scripts.supabase_exit.d1_verify import all_verified, verify_tables
from scripts.supabase_exit.pg_dump_split import batch_inserts, local_insert, split_dump_file


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--dump", required=True, help="local pg_dump --column-inserts file (ticket-0 snapshot)"
    )
    parser.add_argument("--db", required=True, help="local target SQLite file (created if missing)")
    parser.add_argument(
        "--batch-size", type=int, default=500, help="INSERTs per transaction (default: 500)"
    )
    parser.add_argument(
        "--tables", default="", help="comma-separated subset of tables (default: all in dump)"
    )
    parser.add_argument(
        "--dry-run", action="store_true", help="parse and count only; write nothing"
    )
    return parser


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    try:
        split = split_dump_file(args.dump)
    except (ValueError, FileNotFoundError, OSError) as exc:
        print(f"error: {exc}", file=sys.stderr)
        return 2

    wanted = {t.strip() for t in args.tables.split(",") if t.strip()}
    unknown = wanted - set(split.tables)
    if unknown:
        print(f"error: tables not in dump: {sorted(unknown)}", file=sys.stderr)
        return 2
    tables = {t: s for t, s in split.tables.items() if not wanted or t in wanted}
    if not tables:
        print(
            "error: no migration payload (no INSERT statements for the selected tables)",
            file=sys.stderr,
        )
        return 2

    batches = batch_inserts(tables, batch_size=args.batch_size)
    summary: dict[str, object] = {
        "dump": str(Path(args.dump)),
        "tables": sorted(tables),
        "dump_statements": sum(len(s) for s in tables.values()),
        "batches": len(batches),
        "skipped_lines": split.skipped_lines,
        "dry_run": args.dry_run,
    }
    summary["source_rows"] = {table: len(stmts) for table, stmts in tables.items()}
    summary["source_checksums"] = {
        table: hashlib.sha256("\n".join(sorted(stmts)).encode()).hexdigest()
        for table, stmts in tables.items()
    }

    if args.dry_run:
        print(json.dumps(summary, indent=2, sort_keys=True))
        return 0

    target = open_local_db(args.db)
    source_replay = _replay_source(tables)
    try:
        reports = import_batches(target, batches)
        summary["imported"] = {
            r.table: {"batches": r.batches, "statements": r.statements, "rows": r.rows}
            for r in reports
        }
        verifications = verify_tables(source=source_replay, target=target, tables=sorted(tables))
        summary["verification"] = [
            {
                "table": v.table,
                "source_rows": v.source_rows,
                "target_rows": v.target_rows,
                "source_checksum": v.source_checksum,
                "target_checksum": v.target_checksum,
                "verified": v.verified,
            }
            for v in verifications
        ]
        ok = all_verified(verifications)
        summary["verified"] = ok
        print(json.dumps(summary, indent=2, sort_keys=True))
        return 0 if ok else 1
    finally:
        target.close()
        source_replay.close()


def _replay_source(tables: dict[str, list[str]]) -> sqlite3.Connection:
    """Replay dump INSERTs into a scratch DB so both sides share one canonicaliser."""
    conn = sqlite3.connect(":memory:")
    for table, stmts in tables.items():
        # Permissive staging schema from the first INSERT's column list, so
        # the source side holds the same rows the target receives.
        cols = _insert_columns(stmts[0])
        conn.execute(f'CREATE TABLE "{table}" ({", ".join(f"{c} TEXT" for c in cols)})')
        with conn:
            for stmt in stmts:
                conn.execute(local_insert(stmt))
    return conn


def _insert_columns(insert_sql: str) -> list[str]:
    inner = insert_sql.split("(", 1)[1].split(")", 1)[0]
    return [c.strip().strip('"') for c in inner.split(",") if c.strip()]


if __name__ == "__main__":
    raise SystemExit(main())
