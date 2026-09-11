#!/usr/bin/env python3
"""Advisory post-archive DB size gate (issue #3811).

Read-only: reports per-table and whole-DB sizes after the checkpoint
archive so operators can verify the expected size relief. Fail-open by
design — DB errors exit 0 unless --strict is passed, so this step can
never fail the archive workflow (it also runs with continue-on-error).

See docs/ops/checkpoint-archive-vacuum.md for the VACUUM strategy and
the manual pre/post measurement queries.
"""

from __future__ import annotations

import argparse
import os
import sys

PG_URI_ENV = "CORE_POSTGRES_URI"

# Tables whose footprint the archive is expected to shrink.
GATED_TABLES = (
    "checkpoints",
    "checkpoint_writes",
    "checkpoint_blobs",
    "documents",
    "archive_objects",
)

_VALUES = ", ".join(f"('{t}')" for t in GATED_TABLES)
SIZE_SQL = (
    "SELECT relname AS table_name,"
    " pg_total_relation_size('public.' || relname) AS total_bytes"
    f" FROM (VALUES {_VALUES}) AS t(relname) ORDER BY relname"
)

DB_SIZE_SQL = "SELECT pg_database_size(current_database()) AS db_bytes"


def evaluate_sizes(
    sizes_mb: dict[str, float], db_mb: float, threshold_mb: float
) -> tuple[bool, str]:
    """Pure gate logic: ok unless the whole-DB size exceeds the threshold."""
    lines = [f"{name}: {size:.1f} MB" for name, size in sizes_mb.items()]
    lines.append(f"database total: {db_mb:.1f} MB (threshold {threshold_mb:.1f} MB)")
    if db_mb > threshold_mb:
        return False, "SIZE GATE EXCEEDED\n" + "\n".join(lines)
    return True, "size gate ok\n" + "\n".join(lines)


def read_sizes(pg_uri: str) -> tuple[dict[str, float], float]:
    """Read-only size snapshot over a direct Postgres connection."""
    import psycopg

    sizes: dict[str, float] = {}
    with psycopg.connect(pg_uri) as conn, conn.cursor() as cur:
        cur.execute(SIZE_SQL)
        for name, total_bytes in cur.fetchall():
            sizes[str(name)] = int(total_bytes) / (1024 * 1024)
        cur.execute(DB_SIZE_SQL)
        db_mb = int(cur.fetchone()[0]) / (1024 * 1024)
    return sizes, db_mb


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--threshold-mb", type=float, default=500.0)
    parser.add_argument("--strict", action="store_true", help="exit 2 on DB errors or gate breach")
    args = parser.parse_args(argv)

    pg_uri = (os.environ.get(PG_URI_ENV) or "").strip()
    if not pg_uri:
        print(f"size gate: {PG_URI_ENV} not set; skipping (fail-open)")
        return 2 if args.strict else 0
    try:
        sizes, db_mb = read_sizes(pg_uri)
    except Exception as exc:  # fail-open: a broken meter must not fail the archive
        print(f"size gate: could not read sizes ({exc}); skipping (fail-open)")
        return 2 if args.strict else 0

    ok, report = evaluate_sizes(sizes, db_mb, args.threshold_mb)
    print(report)
    if ok:
        return 0
    return 2 if args.strict else 1


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
