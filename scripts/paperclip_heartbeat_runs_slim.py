#!/usr/bin/env python3
"""Reclaim the TOAST space of paperclip's heartbeat_runs.context_snapshot (DIG-4821).

The heartbeat scheduler reads the issue and task ids out of the context snapshot
of every candidate run. The snapshot is a TOASTed jsonb document of tens of
kilobytes, so the read detoasted the whole document for every row and starved
the API connection pool (DIG-4762).

This is the one-off cleanup of the rows that already exist. It rewrites every
snapshot with the same transform the paperclip trigger applies to new writes
(paperclip migration 0308, function
`paperclip_slim_heartbeat_run_context_snapshot`), in batches, and reports the
TOAST footprint and the scheduler query plan before and after.

It is idempotent: a row whose snapshot is already slim is left untouched, so a
second run rewrites nothing and reports zero updated rows.

Usage:

    PAPERCLIP_DATABASE_URL=... python scripts/paperclip_heartbeat_runs_slim.py --dry-run
    PAPERCLIP_DATABASE_URL=... python scripts/paperclip_heartbeat_runs_slim.py
    PGPASSWORD=... python scripts/paperclip_heartbeat_runs_slim.py \
        --host 127.0.0.1 --port 54329 --user paperclip --dbname paperclip

The password is never a command line argument. It is read from an environment
variable, so it lands neither in the shell history nor in the process list.

`--drop-continuation` additionally removes the top-level `executionContinuation`
and `paperclipContinuationSummary` copies. The paperclip trigger keeps them on
purpose: the resume path reads `previousRun.context.executionContinuation.messages`
to compute the resume delta. Dropping them does not crash the resume, it makes
the resume fall back to a full bootstrap instead of a provider-conversation
resume. That is why it is opt-in and not the default.

See docs/ops/heartbeat-runs-retention.md for the retention policy that follows
this cleanup.
"""

from __future__ import annotations

import argparse
import json
import os
import sys
import time
import uuid
from datetime import datetime, timedelta, timezone
from typing import Any

DSN_ENV = "PAPERCLIP_DATABASE_URL"
DEFAULT_PASSWORD_ENV = "PGPASSWORD"

RUNS_TABLE = "heartbeat_runs"
EVENTS_TABLE = "heartbeat_run_events"

# The rendered prompt is rebuilt at dispatch time. Storing it a second time in
# the snapshot of the run is what made the snapshot tens of kilobytes.
TOP_LEVEL_MARKDOWN_KEYS = (
    "paperclipTaskMarkdown",
    "paperclipTaskMarkdownCompact",
    "paperclipTaskMarkdownAssignment",
    "paperclipTaskMarkdownAssignmentCompact",
    "paperclipWakeComment",
    "paperclipFreshSessionHandoffMarkdown",
)

# The wake payload keeps the small proof fields that the merge and the external
# chat presentation read. It drops the copies of the issue, of the comments and
# of the continuation, because the snapshot already holds them.
WAKE_DROP_KEYS = ("executionContinuation", "continuationSummary")

# The top-level copies are NOT dropped by the paperclip trigger: the resume
# path reads them. They are the largest single top-level key, so the cleanup
# can drop them with `--drop-continuation`.
TOP_LEVEL_CONTINUATION_KEYS = ("executionContinuation", "paperclipContinuationSummary")

# The columns the paperclip migration 0308 adds. When they are present the
# cleanup keeps them in sync, so the rows stay correct even before the trigger
# is installed.
ID_COLUMNS = ("context_issue_id", "context_task_id")


# --------------------------------------------------------------------------
# Pure helpers
# --------------------------------------------------------------------------


def slim_snapshot(snapshot: Any, *, drop_continuation: bool = False) -> Any:
    """The reference transform, in Python.

    The SQL function built by `build_slim_function_sql` must agree with this
    exactly. `verify_transform` checks that on live rows before anything is
    written, so the two can never drift apart silently.
    """
    if not isinstance(snapshot, dict):
        return snapshot
    dropped = set(TOP_LEVEL_MARKDOWN_KEYS)
    if drop_continuation:
        dropped |= set(TOP_LEVEL_CONTINUATION_KEYS)
    slim = {key: value for key, value in snapshot.items() if key not in dropped}
    wake = slim.get("paperclipWake")
    if isinstance(wake, dict):
        slim_wake = {key: value for key, value in wake.items() if key not in WAKE_DROP_KEYS}
        issue = slim_wake.get("issue")
        if isinstance(issue, dict) and isinstance(issue.get("id"), str):
            slim_wake["issue"] = {"id": issue["id"]}
        slim["paperclipWake"] = slim_wake
    return slim


def build_slim_function_sql(*, drop_continuation: bool = False) -> str:
    """The SQL twin of `slim_snapshot`, as a session-local function.

    `pg_temp` keeps the function out of the database: it lives for this session
    only and disappears with it, so the cleanup leaves nothing behind in the
    schema.
    """
    top_level = list(TOP_LEVEL_MARKDOWN_KEYS)
    if drop_continuation:
        top_level += list(TOP_LEVEL_CONTINUATION_KEYS)
    drops = "\n".join(f"    - '{key}'::text" for key in top_level)
    return f"""
CREATE OR REPLACE FUNCTION pg_temp.paperclip_slim_snapshot(snap jsonb)
RETURNS jsonb
LANGUAGE plpgsql
AS $paperclip$
DECLARE
  slim_snapshot jsonb;
  slim_wake jsonb;
BEGIN
  IF snap IS NULL THEN
    RETURN NULL;
  END IF;

  slim_snapshot := snap
{drops};

  -- The parentheses matter. In PL/pgSQL the arrow binds weaker than the minus
  -- sign, so an unparenthesized arrow would swallow the keys.
  IF jsonb_typeof(slim_snapshot -> 'paperclipWake') = 'object' THEN
    slim_wake := (slim_snapshot -> 'paperclipWake')
      - 'executionContinuation'::text
      - 'continuationSummary'::text;
    IF jsonb_typeof(slim_wake -> 'issue') = 'object'
      AND jsonb_typeof(slim_wake -> 'issue' -> 'id') = 'string' THEN
      slim_wake := jsonb_set(slim_wake, '{{issue}}', jsonb_build_object('id', slim_wake -> 'issue' -> 'id'));
    END IF;
    slim_snapshot := jsonb_set(slim_snapshot, '{{paperclipWake}}', slim_wake);
  END IF;

  RETURN slim_snapshot;
END;
$paperclip$;
""".strip()


def build_batch_update_sql(*, set_id_columns: bool) -> str:
    """The batched, idempotent rewrite of one batch of runs.

    The batch is materialised once, so every row is detoasted once and the
    transform is computed once. The `IS DISTINCT FROM` guard is what makes the
    cleanup idempotent: a row that is already slim is not written, so it does
    not leave a dead tuple behind either.
    """
    set_clause = "context_snapshot = s.slim"
    if set_id_columns:
        set_clause += (
            ",\n       context_issue_id = nullif(s.slim ->> 'issueId', '')"
            ",\n       context_task_id = nullif(s.slim ->> 'taskId', '')"
        )
    return f"""
WITH batch AS MATERIALIZED (
  SELECT id, context_snapshot
    FROM {RUNS_TABLE}
   WHERE id > %(cursor)s
     AND created_at < %(cutoff)s::timestamptz
   ORDER BY id
   LIMIT %(batch_size)s
), slimmed AS MATERIALIZED (
  SELECT id,
         context_snapshot AS original,
         pg_temp.paperclip_slim_snapshot(context_snapshot) AS slim
    FROM batch
), upd AS (
  UPDATE {RUNS_TABLE} AS r
     SET {set_clause}
    FROM slimmed AS s
   WHERE r.id = s.id
     AND s.slim IS DISTINCT FROM s.original
  RETURNING r.id
)
SELECT (SELECT count(*) FROM batch) AS scanned,
       (SELECT count(*) FROM upd) AS updated,
       -- `max()` is not defined for uuid, so the cursor is the last id by order
       (SELECT id FROM batch ORDER BY id DESC LIMIT 1) AS last_id
""".strip()


def build_batch_dry_run_sql() -> str:
    """The same batch, counted instead of written."""
    return f"""
WITH batch AS MATERIALIZED (
  SELECT id, context_snapshot
    FROM {RUNS_TABLE}
   WHERE id > %(cursor)s
     AND created_at < %(cutoff)s::timestamptz
   ORDER BY id
   LIMIT %(batch_size)s
), slimmed AS MATERIALIZED (
  SELECT id,
         context_snapshot AS original,
         pg_temp.paperclip_slim_snapshot(context_snapshot) AS slim
    FROM batch
)
SELECT count(*) AS scanned,
       count(*) FILTER (WHERE slim IS DISTINCT FROM original) AS updated,
       coalesce(sum(pg_column_size(original)), 0) AS original_bytes,
       coalesce(sum(pg_column_size(slim)), 0) AS slim_bytes,
       -- `max()` is not defined for uuid, so the cursor is the last id by order
       (SELECT id FROM batch ORDER BY id DESC LIMIT 1) AS last_id
FROM slimmed
""".strip()


def resolve_connection(args: argparse.Namespace, env: dict[str, str]) -> tuple[str, dict[str, str]]:
    """The connection string and the keyword arguments for psycopg.connect.

    The password comes from an environment variable, never from the command
    line, so it never appears in the process list.
    """
    dsn = (args.dsn or env.get(DSN_ENV) or "").strip()
    if dsn:
        return dsn, {}
    conninfo = f"host={args.host} port={args.port} dbname={args.dbname}"
    if args.user:
        conninfo += f" user={args.user}"
    password = env.get(args.password_env, "")
    return conninfo, ({"password": password} if password else {})


def redact_dsn(dsn: str) -> str:
    """Hide the password in a DSN before it is printed."""
    if "://" in dsn:
        scheme, _, rest = dsn.partition("://")
        if "@" in rest:
            userinfo, _, hostpart = rest.rpartition("@")
            user, _, _password = userinfo.partition(":")
            return f"{scheme}://{user}:***@{hostpart}"
        return dsn
    parts = []
    for chunk in dsn.split():
        key, sep, _value = chunk.partition("=")
        parts.append(f"{key}=***" if sep and key == "password" else chunk)
    return " ".join(parts)


def format_bytes(value: Any) -> str:
    """A byte count as a human readable string."""
    if value is None:
        return "n/a"
    number = float(value)
    for unit in ("B", "KiB", "MiB", "GiB", "TiB"):
        if abs(number) < 1024 or unit == "TiB":
            if unit == "B":
                return f"{int(number):,} B"
            return f"{number:,.2f} {unit}"
        number /= 1024
    return f"{number:.2f} TiB"


def resolve_cutoff(older_than_days: float) -> str | datetime:
    """The `created_at` upper bound of the batches.

    Zero days means every row, which is expressed as the infinite timestamp so
    the predicate stays a plain comparison the planner can use.
    """
    if older_than_days <= 0:
        return "infinity"
    return datetime.now(timezone.utc) - timedelta(days=older_than_days)


def summarise_sizes(sizes: dict[str, Any]) -> dict[str, Any]:
    """The headline numbers of a size snapshot."""
    runs_total = int(sizes.get("runs_total_bytes") or 0)
    runs_toast = int(sizes.get("runs_toast_bytes") or 0)
    return {
        "runs_total_bytes": runs_total,
        "runs_toast_bytes": runs_toast,
        "runs_heap_bytes": int(sizes.get("runs_heap_bytes") or 0),
        "events_total_bytes": int(sizes.get("events_total_bytes") or 0),
        "events_toast_bytes": int(sizes.get("events_toast_bytes") or 0),
        "db_bytes": int(sizes.get("db_bytes") or 0),
    }


def plan_difference(before: dict[str, Any], after: dict[str, Any]) -> dict[str, Any]:
    """The difference between two size snapshots, in bytes."""
    return {
        "runs_toast_freed_bytes": int(before["runs_toast_bytes"]) - int(after["runs_toast_bytes"]),
        "runs_total_freed_bytes": int(before["runs_total_bytes"]) - int(after["runs_total_bytes"]),
        "db_freed_bytes": int(before["db_bytes"]) - int(after["db_bytes"]),
    }


# --------------------------------------------------------------------------
# Database access
# --------------------------------------------------------------------------


SIZES_SQL = """
SELECT
  pg_relation_size('public.heartbeat_runs') AS runs_heap_bytes,
  pg_total_relation_size('public.heartbeat_runs') AS runs_total_bytes,
  (SELECT pg_total_relation_size(reltoastrelid)
     FROM pg_class WHERE oid = 'public.heartbeat_runs'::regclass) AS runs_toast_bytes,
  pg_total_relation_size('public.heartbeat_run_events') AS events_total_bytes,
  (SELECT pg_total_relation_size(reltoastrelid)
     FROM pg_class WHERE oid = 'public.heartbeat_run_events'::regclass) AS events_toast_bytes,
  pg_database_size(current_database()) AS db_bytes
""".strip()


PAYLOAD_SQL = """
SELECT count(*) AS rows,
       count(context_snapshot) AS rows_with_snapshot,
       coalesce(sum(pg_column_size(context_snapshot)), 0) AS payload_bytes,
       coalesce(avg(pg_column_size(context_snapshot)), 0)::bigint AS avg_payload_bytes,
       coalesce(max(pg_column_size(context_snapshot)), 0) AS max_payload_bytes,
       min(created_at) AS oldest_run,
       max(created_at) AS newest_run
  FROM heartbeat_runs
""".strip()


EXHAUSTED_RUNS_SQL = """
WITH latest_exhaustion AS (
  SELECT DISTINCT ON (run_id) run_id, id AS event_id
    FROM heartbeat_run_events
   WHERE company_id = %(company_id)s
     AND event_type = 'lifecycle'
     AND message LIKE 'Bounded retry exhausted%%'
   ORDER BY run_id, id DESC
)
SELECT r.agent_id::text AS agent_id, r.created_at
  FROM heartbeat_runs r
  JOIN agents a ON a.id = r.agent_id
  JOIN latest_exhaustion le ON le.run_id = r.id
 WHERE r.company_id = %(company_id)s
   AND a.company_id = %(company_id)s
   AND a.status <> 'terminated'
   AND r.status IN ('failed', 'timed_out')
""".strip()


SCHEDULER_QUERY_SQL = """
SELECT agent_id, created_at,
       context_snapshot ->> 'issueId' AS "runIssueId",
       context_snapshot ->> 'taskId' AS "runTaskId"
  FROM heartbeat_runs
 WHERE company_id = %(company_id)s
   AND agent_id = ANY(%(agent_ids)s::uuid[])
   AND created_at > %(since)s
""".strip()


SCHEDULER_QUERY_COLUMNS_SQL = """
SELECT agent_id, created_at,
       context_issue_id AS "runIssueId",
       context_task_id AS "runTaskId"
  FROM heartbeat_runs
 WHERE company_id = %(company_id)s
   AND agent_id = ANY(%(agent_ids)s::uuid[])
   AND created_at > %(since)s
""".strip()


ID_COLUMN_SQL = """
SELECT column_name
  FROM information_schema.columns
 WHERE table_schema = 'public'
   AND table_name = 'heartbeat_runs'
   AND column_name = ANY(%(names)s::text[])
""".strip()


COMPANY_SQL = """
SELECT id::text
  FROM companies
 ORDER BY (SELECT count(*) FROM heartbeat_runs r WHERE r.company_id = companies.id) DESC,
          created_at
 LIMIT 1
""".strip()


def read_sizes(conn: Any) -> dict[str, Any]:
    """The per-table and per-database footprint."""
    with conn.cursor() as cur:
        cur.execute(SIZES_SQL)
        row = cur.fetchone()
        names = [description.name for description in cur.description]
    return {name: value for name, value in zip(names, row)}


def read_payload_stats(conn: Any) -> dict[str, Any]:
    """The live size of the stored snapshots."""
    with conn.cursor() as cur:
        cur.execute(PAYLOAD_SQL)
        row = cur.fetchone()
        names = [description.name for description in cur.description]
    return {name: value for name, value in zip(names, row)}


def read_id_columns(conn: Any) -> list[str]:
    """The context id columns, when the paperclip migration has added them."""
    with conn.cursor() as cur:
        cur.execute(ID_COLUMN_SQL, {"names": list(ID_COLUMNS)})
        return {row[0] for row in cur.fetchall()}


def read_scheduler_params(conn: Any, company_id: str | None) -> dict[str, Any]:
    """The parameters the attention feed uses for the scheduler query.

    They mirror `listAttentionExhaustedRuns` and the feed builder in
    `server/src/services/attention.ts`: the company, the agents whose runs
    exhausted their retries, and the oldest created_at among those runs.
    """
    with conn.cursor() as cur:
        if company_id is None:
            cur.execute(COMPANY_SQL)
            row = cur.fetchone()
            if row is None:
                raise RuntimeError("no company found")
            company_id = str(row[0])
        cur.execute(EXHAUSTED_RUNS_SQL, {"company_id": company_id})
        rows = cur.fetchall()
    agent_ids = sorted({str(agent_id) for agent_id, _created_at in rows})
    created_ats = [created_at for _agent_id, created_at in rows if created_at is not None]
    since = min(created_ats) if created_ats else datetime.now(timezone.utc)
    return {
        "company_id": company_id,
        "agent_ids": agent_ids,
        "since": since,
        "exhausted_runs": len(rows),
    }


def capture_scheduler_plan(conn: Any, params: dict[str, Any], *, use_id_columns: bool) -> list[str]:
    """The `EXPLAIN (ANALYZE, BUFFERS)` plan of the scheduler query."""
    sql = SCHEDULER_QUERY_COLUMNS_SQL if use_id_columns else SCHEDULER_QUERY_SQL
    query_params = {
        "company_id": params["company_id"],
        "agent_ids": [uuid.UUID(agent_id) for agent_id in params["agent_ids"]],
        "since": params["since"],
    }
    with conn.cursor() as cur:
        cur.execute("EXPLAIN (ANALYZE, BUFFERS, SETTINGS) " + sql, query_params)
        return [str(row[0]) for row in cur.fetchall()]


def verify_transform(conn: Any, *, drop_continuation: bool, sample_size: int) -> int:
    """Check the SQL function against the Python reference on live rows.

    Returns the number of rows compared. A mismatch raises: the cleanup must
    not run on a transform the script and the paperclip trigger disagree about.
    """
    if sample_size <= 0:
        return 0
    bound = uuid.UUID(int=uuid.uuid4().int)
    with conn.cursor() as cur:
        cur.execute(
            """
            SELECT context_snapshot,
                   pg_temp.paperclip_slim_snapshot(context_snapshot) AS slim
              FROM heartbeat_runs
             WHERE id >= %(bound)s AND context_snapshot IS NOT NULL
             ORDER BY id
             LIMIT %(limit)s
            """,
            {"bound": bound, "limit": sample_size},
        )
        rows = cur.fetchall()
    compared = 0
    for original, slim in rows:
        expected = slim_snapshot(original, drop_continuation=drop_continuation)
        if expected != slim:
            raise RuntimeError(
                "the SQL transform and the Python reference disagree; refusing to write"
            )
        compared += 1
    return compared


def run_cleanup(
    conn: Any,
    *,
    update_sql: str,
    dry_run_sql: str,
    dry_run: bool,
    batch_size: int,
    cutoff: str | datetime,
    pause_seconds: float,
    max_rows: int,
    max_batches: int,
) -> dict[str, Any]:
    """Walk the table once, in batches, and rewrite the fat snapshots."""
    cursor = uuid.UUID(int=0)
    scanned = 0
    updated = 0
    batches = 0
    original_bytes = 0
    slim_bytes = 0
    while True:
        if max_batches and batches >= max_batches:
            break
        if max_rows and scanned >= max_rows:
            break
        params = {
            "cursor": cursor,
            "cutoff": cutoff,
            "batch_size": batch_size,
        }
        with conn.cursor() as cur:
            if dry_run:
                cur.execute(dry_run_sql, params)
                row = cur.fetchone()
                batch_scanned = int(row[0])
                batch_updated = int(row[1])
                original_bytes += int(row[2])
                slim_bytes += int(row[3])
                last_id = row[4]
            else:
                cur.execute(update_sql, params)
                row = cur.fetchone()
                batch_scanned = int(row[0])
                batch_updated = int(row[1])
                last_id = row[2]
        batches += 1
        scanned += batch_scanned
        updated += batch_updated
        if not batch_scanned:
            break
        if last_id is not None:
            cursor = last_id if isinstance(last_id, uuid.UUID) else uuid.UUID(str(last_id))
        if not dry_run:
            print(
                f"  batch {batches}: scanned {batch_scanned}, rewritten {batch_updated}",
                flush=True,
            )
        if pause_seconds > 0 and batch_scanned:
            time.sleep(pause_seconds)
    return {
        "batches": batches,
        "scanned": scanned,
        "updated": updated,
        "original_bytes": original_bytes,
        "slim_bytes": slim_bytes,
    }


def run_vacuum(conn: Any, *, full: bool, lock_timeout_ms: int) -> str:
    """Reclaim the dead tuples.

    Plain VACUUM returns the space to the free space map for reuse but keeps
    the files. VACUUM FULL rewrites the table and its TOAST, which returns the
    bytes to the filesystem but takes an ACCESS EXCLUSIVE lock, so it is
    guarded by a lock timeout.
    """
    statement = "VACUUM FULL" if full else "VACUUM (ANALYZE)"
    with conn.cursor() as cur:
        cur.execute(f"SET lock_timeout = '{lock_timeout_ms}ms'")
        try:
            cur.execute(f"{statement} {RUNS_TABLE}")
        finally:
            cur.execute("SET lock_timeout = 0")
    return statement


# --------------------------------------------------------------------------
# CLI
# --------------------------------------------------------------------------


def parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--dsn", help=f"full connection string (default: ${DSN_ENV})")
    parser.add_argument("--host", default="127.0.0.1")
    parser.add_argument("--port", type=int, default=54329)
    parser.add_argument("--user", default="paperclip")
    parser.add_argument("--dbname", default="paperclip")
    parser.add_argument(
        "--password-env",
        default=DEFAULT_PASSWORD_ENV,
        help=f"environment variable holding the password (default: {DEFAULT_PASSWORD_ENV})",
    )
    parser.add_argument("--company-id", help="company to explain (default: the busiest one)")
    parser.add_argument("--batch-size", type=int, default=200, help="rows per transaction")
    parser.add_argument(
        "--pause-seconds",
        type=float,
        default=0.2,
        help="pause between batches, so the scheduler keeps its share of the database",
    )
    parser.add_argument("--statement-timeout-ms", type=int, default=120_000)
    parser.add_argument("--lock-timeout-ms", type=int, default=5_000)
    parser.add_argument("--max-rows", type=int, default=0, help="0 means no limit")
    parser.add_argument("--max-batches", type=int, default=0, help="0 means no limit")
    parser.add_argument(
        "--older-than-days",
        type=float,
        default=0.0,
        help="only touch runs older than this many days (0 means every run)",
    )
    parser.add_argument(
        "--drop-continuation",
        action="store_true",
        help="also drop the top-level executionContinuation copies (breaks the resume delta)",
    )
    parser.add_argument("--dry-run", action="store_true", help="count, do not write")
    parser.add_argument(
        "--verify-sample",
        type=int,
        default=25,
        help="rows to compare against the Python reference before writing (0 skips)",
    )
    parser.add_argument("--vacuum", action="store_true", help="VACUUM (ANALYZE) afterwards")
    parser.add_argument(
        "--vacuum-full", action="store_true", help="VACUUM FULL afterwards (ACCESS EXCLUSIVE)"
    )
    parser.add_argument("--skip-plan", action="store_true", help="do not capture the query plans")
    parser.add_argument("--json-out", help="write the full report as JSON here")
    return parser.parse_args(argv)


def main(argv: list[str] | None = None) -> int:
    args = parse_args(argv)
    env = dict(os.environ)
    conninfo, connect_kwargs = resolve_connection(args, env)

    try:
        import psycopg
    except ImportError:
        print(
            "psycopg is not installed. Install it with: pip install 'psycopg[binary]'",
            file=sys.stderr,
        )
        return 2

    print("paperclip heartbeat_runs snapshot cleanup (DIG-4821)")
    print(f"  target: {redact_dsn(conninfo)}")
    if args.drop_continuation:
        print("  transform: markdown keys + wake copies + top-level continuation copies")
    else:
        print("  transform: markdown keys + wake copies (the paperclip trigger transform)")
    if args.dry_run:
        print("  mode: dry run, nothing is written")

    try:
        with psycopg.connect(conninfo, autocommit=True, **connect_kwargs) as conn:
            with conn.cursor() as cur:
                cur.execute(f"SET statement_timeout = '{args.statement_timeout_ms}ms'")
                cur.execute(build_slim_function_sql(drop_continuation=args.drop_continuation))

            compared = verify_transform(
                conn, drop_continuation=args.drop_continuation, sample_size=args.verify_sample
            )
            print(f"  verified the SQL transform against the Python reference on {compared} rows")

            id_columns = read_id_columns(conn)
            has_id_columns = bool(id_columns)
            print(
                "  context id columns: "
                + (", ".join(sorted(id_columns)) if has_id_columns else "not present yet")
            )

            params = read_scheduler_params(conn, args.company_id)
            print(
                f"  scheduler parameters: {len(params['agent_ids'])} agents, "
                f"since {params['since']}, {params['exhausted_runs']} exhausted runs"
            )

            before_sizes = summarise_sizes(read_sizes(conn))
            before_payload = read_payload_stats(conn)
            before_plan: list[str] = []
            if not args.skip_plan:
                before_plan = capture_scheduler_plan(conn, params, use_id_columns=False)
                if has_id_columns:
                    before_plan += [
                        "",
                        "-- same query on the real columns --",
                    ] + capture_scheduler_plan(conn, params, use_id_columns=True)

            print(
                "  before: TOAST "
                f"{format_bytes(before_sizes['runs_toast_bytes'])}, table "
                f"{format_bytes(before_sizes['runs_total_bytes'])}, live payload "
                f"{format_bytes(before_payload['payload_bytes'])} in {before_payload['rows']} rows"
            )

            cutoff = resolve_cutoff(args.older_than_days)
            result = run_cleanup(
                conn,
                update_sql=build_batch_update_sql(set_id_columns=has_id_columns),
                dry_run_sql=build_batch_dry_run_sql(),
                dry_run=args.dry_run,
                batch_size=args.batch_size,
                cutoff=cutoff,
                pause_seconds=args.pause_seconds,
                max_rows=args.max_rows,
                max_batches=args.max_batches,
            )

            vacuum_statement = None
            if not args.dry_run and (args.vacuum or args.vacuum_full):
                vacuum_statement = run_vacuum(
                    conn, full=args.vacuum_full, lock_timeout_ms=args.lock_timeout_ms
                )
                print(f"  ran {vacuum_statement} {RUNS_TABLE}")

            after_sizes = summarise_sizes(read_sizes(conn))
            after_payload = read_payload_stats(conn)
            after_plan: list[str] = []
            if not args.skip_plan:
                after_plan = capture_scheduler_plan(conn, params, use_id_columns=False)
                if has_id_columns:
                    after_plan += [
                        "",
                        "-- same query on the real columns --",
                    ] + capture_scheduler_plan(conn, params, use_id_columns=True)

            difference = plan_difference(before_sizes, after_sizes)
            report = {
                "target": redact_dsn(conninfo),
                "dry_run": bool(args.dry_run),
                "drop_continuation": bool(args.drop_continuation),
                "older_than_days": args.older_than_days,
                "batch_size": args.batch_size,
                "verified_rows": compared,
                "cleanup": result,
                "vacuum": vacuum_statement,
                "before": {"sizes": before_sizes, "payload": before_payload},
                "after": {"sizes": after_sizes, "payload": after_payload},
                "difference": difference,
                "scheduler_params": {
                    "company_id": params["company_id"],
                    "agent_count": len(params["agent_ids"]),
                    "since": str(params["since"]),
                    "exhausted_runs": params["exhausted_runs"],
                },
                "plan_before": before_plan,
                "plan_after": after_plan,
            }

            print("")
            print(f"  rows scanned: {result['scanned']}, rewritten: {result['updated']}")
            print(
                "  after: TOAST "
                f"{format_bytes(after_sizes['runs_toast_bytes'])}, table "
                f"{format_bytes(after_sizes['runs_total_bytes'])}, live payload "
                f"{format_bytes(after_payload['payload_bytes'])} in {after_payload['rows']} rows"
            )
            print(
                "  TOAST freed: "
                f"{format_bytes(difference['runs_toast_freed_bytes'])}, "
                "table freed: "
                f"{format_bytes(difference['runs_total_freed_bytes'])}, "
                "database freed: "
                f"{format_bytes(difference['db_freed_bytes'])}"
            )

            if args.json_out:
                with open(args.json_out, "w", encoding="utf-8") as handle:
                    json.dump(report, handle, indent=2, default=str)
                print(f"  wrote the report to {args.json_out}")
    except Exception as exc:
        # The report is the point of the run: a failure must be loud and named.
        print(f"cleanup failed: {exc}", file=sys.stderr)
        return 1

    return 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
