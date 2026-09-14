#!/usr/bin/env python3
"""Post-archive DB size-relief gate (issue #3968, follow-up to #3811/#3832).

Read-only: compares a pre-archive per-table snapshot with a post-VACUUM one
and FAILS when the gated tables did not shrink. An absolute whole-DB ceiling
is kept as a secondary guard. DB errors fail open by default but fail loud
under --strict.

Why this is operator-run rather than a trailing archive step: the 13:30 UTC
archive NULLs bytea cells, but plain VACUUM (pg_cron 05:50 UTC) is what makes
the space reusable, so relief is only measurable ~16h later. A same-run gate
would false-fail. Capture the pre snapshot with --snapshot-out before the
archive, then compare with --pre-snapshot after the next morning's vacuum.

See docs/ops/checkpoint-archive-vacuum.md for the VACUUM strategy.
"""

from __future__ import annotations

import argparse
import json
import os
import sys
from pathlib import Path

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


def evaluate_relief(
    pre_mb: dict[str, float],
    post_mb: dict[str, float],
    db_mb: float,
    threshold_mb: float,
    min_relief_mb: float = 0.0,
) -> tuple[bool, str]:
    """Pure gate logic: ok only if the gated tables shrank and DB is under ceiling."""
    names = sorted(set(pre_mb) | set(post_mb))
    lines: list[str] = []
    pre_total = post_total = 0.0
    for name in names:
        before = float(pre_mb.get(name, 0.0))
        after = float(post_mb.get(name, 0.0))
        pre_total += before
        post_total += after
        lines.append(f"{name}: {before:.1f} -> {after:.1f} MB ({after - before:+.1f})")
    relief = pre_total - post_total
    lines.append(
        f"gated tables: {pre_total:.1f} -> {post_total:.1f} MB "
        f"(relief {relief:+.1f} MB, minimum {min_relief_mb:.1f} MB)"
    )
    lines.append(f"database total: {db_mb:.1f} MB (ceiling {threshold_mb:.1f} MB)")

    if relief <= 0:
        return False, "RELIEF GATE FAILED: gated tables did not shrink\n" + "\n".join(lines)
    if relief < min_relief_mb:
        return False, (
            f"RELIEF GATE FAILED: relief {relief:.1f} MB is below the "
            f"{min_relief_mb:.1f} MB minimum\n" + "\n".join(lines)
        )
    if db_mb > threshold_mb:
        return False, "SIZE CEILING EXCEEDED\n" + "\n".join(lines)
    return True, "size relief gate ok\n" + "\n".join(lines)


def snapshot_to_json(sizes: dict[str, float], db_mb: float) -> str:
    return json.dumps({"db_mb": db_mb, "tables": sizes}, indent=2, sort_keys=True)


def load_snapshot(path: str | Path) -> tuple[dict[str, float], float]:
    data = json.loads(Path(path).read_text(encoding="utf-8"))
    tables = {str(k): float(v) for k, v in dict(data.get("tables", {})).items()}
    return tables, float(data.get("db_mb", 0.0))


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
    parser.add_argument(
        "--min-relief-mb", type=float, default=0.0, help="minimum gated-table shrink required"
    )
    mode = parser.add_mutually_exclusive_group(required=True)
    mode.add_argument("--pre-snapshot", help="pre-archive snapshot JSON to compare against")
    mode.add_argument(
        "--snapshot-out", help="write the current snapshot here (pre-archive capture) and exit"
    )
    parser.add_argument("--strict", action="store_true", help="exit 2 on DB errors or gate breach")
    args = parser.parse_args(argv)

    pg_uri = (os.environ.get(PG_URI_ENV) or "").strip()
    if not pg_uri:
        print(f"size gate: {PG_URI_ENV} not set; skipping (fail-open)")
        return 2 if args.strict else 0
    try:
        sizes, db_mb = read_sizes(pg_uri)
    except Exception as exc:
        if args.strict:
            print(f"size gate: FAILED to read sizes ({exc})", file=sys.stderr)
            return 2
        print(f"size gate: could not read sizes ({exc}); skipping (fail-open)", file=sys.stderr)
        return 0

    if args.snapshot_out:
        out_path = Path(args.snapshot_out)
        out_path.write_text(snapshot_to_json(sizes, db_mb), encoding="utf-8")
        print(f"size gate: wrote pre-archive snapshot to {out_path}")
        return 0

    try:
        pre_sizes, _pre_db = load_snapshot(args.pre_snapshot)
    except (OSError, ValueError) as exc:
        print(
            f"size gate: could not read pre-snapshot {args.pre_snapshot} ({exc})", file=sys.stderr
        )
        return 2
    ok, report = evaluate_relief(pre_sizes, sizes, db_mb, args.threshold_mb, args.min_relief_mb)
    print(report)
    if ok:
        return 0
    return 2 if args.strict else 1


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
