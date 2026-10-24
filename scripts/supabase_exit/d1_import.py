"""Replay per-table INSERT batches into a local SQLite database (DIG-2893).

Each :class:`TableBatch` runs inside one transaction: all-or-nothing per
batch, so a failure is attributable to exactly one table and one batch and
never leaves a half-written batch behind. The importer creates no schema --
every target table must already exist (DDL comes from tickets 2/3) -- and it
opens only local SQLite files:

* ``:memory:`` is accepted (unit tests);
* any other value must be a local file path -- URLs and remote-looking
  targets raise ``ValueError`` before anything opens.
"""

from __future__ import annotations

import re
import sqlite3
from dataclasses import dataclass
from pathlib import Path

from scripts.supabase_exit.pg_dump_split import TableBatch, local_insert

_URL_LIKE = re.compile(r"^[a-zA-Z][a-zA-Z0-9+.-]*://")


@dataclass(frozen=True)
class ImportReport:
    """Per-table import outcome."""

    table: str
    batches: int
    statements: int
    rows: int


def assert_local_target(db: str) -> str:
    """Refuse anything that is not a local SQLite target."""
    if db != ":memory:" and (_URL_LIKE.match(db) or db.startswith(("\\\\", "//"))):
        raise ValueError(f"refusing non-local target: {db!r}")
    return db


def _row_count(conn: sqlite3.Connection, table: str) -> int:
    return int(conn.execute(f'SELECT COUNT(*) FROM "{table}"').fetchone()[0])


def import_batches(
    conn: sqlite3.Connection,
    batches: list[TableBatch],
) -> list[ImportReport]:
    """Replay batches; returns one report per table. Raises on empty input."""
    if not batches:
        raise ValueError("no batches to import")
    by_table: dict[str, list[TableBatch]] = {}
    for batch in batches:
        by_table.setdefault(batch.table, []).append(batch)
    reports: list[ImportReport] = []
    for table in sorted(by_table):
        table_batches = by_table[table]
        statements = 0
        for batch in table_batches:
            if not batch.statements:
                raise ValueError(f"empty batch for table {table!r}")
            with conn:  # one transaction per batch
                for stmt in batch.statements:
                    conn.execute(local_insert(stmt))
            statements += len(batch.statements)
        reports.append(
            ImportReport(
                table=table,
                batches=len(table_batches),
                statements=statements,
                rows=_row_count(conn, table),
            )
        )
    return reports


def open_local_db(db_path: str) -> sqlite3.Connection:
    """Open a local SQLite file (creating parent dirs); ``:memory:`` allowed."""
    target = assert_local_target(db_path)
    if target != ":memory:":
        Path(target).parent.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(target)
    conn.execute("PRAGMA foreign_keys=ON")
    return conn
