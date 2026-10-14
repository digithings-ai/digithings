"""Row-count + checksum verification of a migrated table set (DIG-2893).

Compares a source database against a target database table by table::

    row counts equal  AND  SHA-256 checksums equal  ->  table VERIFIED

The checksum canonicalises each row as ``json.dumps(row, sort_keys=True)``
with ``None``/numbers/strings preserved by the JSON round-trip, over rows
ordered by every column (``ORDER BY 1..N`` against the target's column list
from ``PRAGMA table_info``). Both sides are read through the same
canonicaliser, so a PG-vs-SQLite type spelling difference (``1`` vs
``1.0``, ``t`` vs ``1``) surfaces as a mismatch to investigate rather than
a silent pass -- the operator then decides whether the difference is a
lossless type mapping or real corruption.

Runs against local SQLite connections only (unit tests use ``:memory:``;
the CLI only opens local files). No network, no credentials.
"""

from __future__ import annotations

import hashlib
import json
import sqlite3
from dataclasses import dataclass


@dataclass(frozen=True)
class TableVerification:
    """Per-table verdict."""

    table: str
    source_rows: int
    target_rows: int
    source_checksum: str
    target_checksum: str

    @property
    def rows_match(self) -> bool:
        """True when source and target hold the same row count."""
        return self.source_rows == self.target_rows

    @property
    def checksums_match(self) -> bool:
        """True when the canonical checksums agree."""
        return self.source_checksum == self.target_checksum

    @property
    def verified(self) -> bool:
        """True only when counts and checksums both agree."""
        return self.rows_match and self.checksums_match


def _columns(conn: sqlite3.Connection, table: str) -> list[str]:
    cols = [row[1] for row in conn.execute(f'PRAGMA table_info("{table}")').fetchall()]
    if not cols:
        raise ValueError(f"table not found in target DDL: {table!r}")
    return cols


def _canonical_rows(conn: sqlite3.Connection, table: str, columns: list[str]) -> list[str]:
    order = ", ".join(f'"{c}"' for c in columns)
    select = ", ".join(f'"{c}"' for c in columns)
    cur = conn.execute(f'SELECT {select} FROM "{table}" ORDER BY {order}')
    return [
        json.dumps(dict(zip(columns, row, strict=True)), sort_keys=True, default=str) for row in cur
    ]


def table_checksum(conn: sqlite3.Connection, table: str) -> tuple[int, str]:
    """Return ``(row_count, sha256_hex)`` for one table."""
    columns = _columns(conn, table)
    canonical = _canonical_rows(conn, table, columns)
    digest = hashlib.sha256("\n".join(canonical).encode("utf-8")).hexdigest()
    return len(canonical), digest


def verify_tables(
    source: sqlite3.Connection,
    target: sqlite3.Connection,
    tables: list[str],
) -> list[TableVerification]:
    """Verify each table in ``tables``; raises ``ValueError`` on empty input."""
    if not tables:
        raise ValueError("no tables to verify")
    results: list[TableVerification] = []
    for table in sorted(tables):
        source_rows, source_checksum = table_checksum(source, table)
        target_rows, target_checksum = table_checksum(target, table)
        results.append(
            TableVerification(
                table=table,
                source_rows=source_rows,
                target_rows=target_rows,
                source_checksum=source_checksum,
                target_checksum=target_checksum,
            )
        )
    return results


def all_verified(results: list[TableVerification]) -> bool:
    """True when every table verified."""
    return bool(results) and all(r.verified for r in results)
