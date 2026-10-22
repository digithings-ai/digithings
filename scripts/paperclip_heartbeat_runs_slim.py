#!/usr/bin/env python3
"""Reclaim the TOAST space of paperclip's heartbeat_runs.context_snapshot (DIG-4821).

The heartbeat scheduler reads the issue and task ids out of the context snapshot
of every candidate run. The snapshot is a TOASTed jsonb document of tens of
kilobytes, so the read detoasted the whole document for every row and starved
the API connection pool (DIG-4762).

This is the one-off cleanup of the rows that already exist. The paperclip
trigger (migration 0308, function `paperclip_slim_heartbeat_run_context_snapshot`)
slims every new snapshot: it keeps every key of the snapshot and replaces the
body of every comment of the top-level `executionContinuation` with a SHA-256
`bodyDigest`. The trigger only touches new writes, so the rows that were
written before it keep the shape they were written with.

This script does not implement that transform a second time. It runs the
trigger itself: it builds a session-local copy of the table, attaches the
trigger function to that copy, and lets the trigger compute the new value. A
row written by this script and a row written by the trigger therefore have the
same shape, because it is the same function that shaped them. When the database
does not carry the trigger yet, the script falls back to a pinned copy of the
migration's function and says so in its output. When the database does carry
the trigger, the script checks that the pinned copy and the installed function
agree on live rows before it writes anything, and refuses to write when they
do not.

It is idempotent: a row whose snapshot is already slim is left untouched, so a
second run rewrites nothing and reports zero updated rows.

Usage:

    PAPERCLIP_DATABASE_URL=... python scripts/paperclip_heartbeat_runs_slim.py --dry-run
    PAPERCLIP_DATABASE_URL=... python scripts/paperclip_heartbeat_runs_slim.py
    PGPASSWORD=... python scripts/paperclip_heartbeat_runs_slim.py \
        --host 127.0.0.1 --port 54329 --user paperclip --dbname paperclip

The password is never a command line argument. It is read from an environment
variable, so it lands neither in the shell history nor in the process list.

See docs/ops/heartbeat-runs-retention.md for the retention policy that follows
this cleanup.
"""

from __future__ import annotations

import argparse
import hashlib
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

# The trigger function of paperclip migration 0308. It is the authority for the
# shape of a slim snapshot: this script runs it, it does not restate it.
TRIGGER_FUNCTION_NAME = "paperclip_slim_heartbeat_run_context_snapshot"

# The pinned copy of that function, kept in this file so the script can run
# against a database that does not carry the trigger yet, and so the drift
# check has something to compare the installed trigger against.
PINNED_FUNCTION_NAME = "paperclip_slim_heartbeat_run_context_snapshot_pinned"
PINNED_TRIGGER_SOURCE = (
    "digithings-ai/paperclip@1c918d30b, "
    "packages/db/src/migrations/0308_heartbeat_run_context_columns.sql"
)

# The session-local copies of the runs table that carry the trigger. The script
# writes the rows through them, so the trigger computes the new value.
PROBE_TABLE = "paperclip_slim_probe"
DRIFT_PROBE_TABLE = "paperclip_slim_probe_pinned"

# The columns the paperclip migration 0308 adds. When they are present the
# cleanup keeps them in sync, so the rows stay correct even before the trigger
# is installed.
ID_COLUMNS = ("context_issue_id", "context_task_id")

# A live table is written while this script runs. PostgreSQL answers a write
# that ran into a concurrent change with one of these SQLSTATEs, and the
# batch is safe to run again, so the batch is retried a few times before the
# run gives up.
BATCH_ATTEMPTS = 3
RETRYABLE_SQLSTATES = frozenset({"40001", "40P01", "55P03", "XX000"})

# The function of migration 0308, verbatim. The pinned copy is what the script
# compares the installed trigger against, and what it runs when the database
# does not carry the trigger yet.
PINNED_TRIGGER_TEMPLATE = """CREATE OR REPLACE FUNCTION pg_temp.{function_name}() RETURNS trigger LANGUAGE plpgsql AS $paperclip$
DECLARE
  slim_snapshot jsonb;
  slim_continuation jsonb;
  slim_messages jsonb;
BEGIN
  -- A snapshot that is not a JSON object has no ids and no envelope. The
  -- mirrored ids are cleared, because a stale id makes a run look like it
  -- belongs to an issue that the snapshot does not name.
  IF NEW.context_snapshot IS NULL OR jsonb_typeof(NEW.context_snapshot) <> 'object' THEN
    NEW.context_issue_id := NULL;
    NEW.context_task_id := NULL;
    RETURN NEW;
  END IF;

  -- The wake payload and the rendered prompt are not touched. Production code
  -- reads the issue work mode, the continuation summary, and the rendered
  -- wake comments from the stored snapshot.
  slim_snapshot := NEW.context_snapshot;

  -- The continuation envelope repeats the body of every comment of the issue.
  -- The bodies live in the comment table, and the envelope needs them only to
  -- find out whether a comment changed. A digest of the body answers that
  -- question and keeps the stored snapshot small.
  IF jsonb_typeof(slim_snapshot -> 'executionContinuation') = 'object' THEN
    slim_continuation := slim_snapshot -> 'executionContinuation';
    IF jsonb_typeof(slim_continuation -> 'messages') = 'array' THEN
      SELECT coalesce(jsonb_agg(
        CASE
          WHEN jsonb_typeof(element.message) = 'object'
            AND jsonb_typeof(element.message -> 'body') = 'string'
          THEN
            (element.message - 'body'::text)
            || jsonb_build_object(
              'bodyDigest',
              encode(sha256(convert_to(element.message ->> 'body', 'UTF8')), 'hex')
            )
          ELSE element.message
        END
      ), '[]'::jsonb)
      INTO slim_messages
      FROM jsonb_array_elements(slim_continuation -> 'messages') AS element(message);
      slim_continuation := (slim_continuation - 'messages'::text)
        || jsonb_build_object('messages', slim_messages);
      slim_snapshot := (slim_snapshot - 'executionContinuation'::text)
        || jsonb_build_object('executionContinuation', slim_continuation);
    END IF;
  END IF;

  NEW.context_snapshot := slim_snapshot;
  -- The ids keep the text form of the snapshot. The read paths that used the
  -- snapshot read the same text, so the mirrored value is the same value.
  NEW.context_issue_id := slim_snapshot ->> 'issueId';
  NEW.context_task_id := slim_snapshot ->> 'taskId';
  RETURN NEW;
END;
$paperclip$;"""


# --------------------------------------------------------------------------
# Pure helpers
# --------------------------------------------------------------------------


def slim_snapshot(snapshot: Any) -> Any:
    """The reference shape of the paperclip trigger, in Python.

    The trigger is the authority. `verify_transform` checks this against the
    trigger itself, on live rows, before anything is written, so the two can
    never drift apart silently.
    """
    if not isinstance(snapshot, dict):
        return snapshot
    continuation = snapshot.get("executionContinuation")
    if not isinstance(continuation, dict):
        return snapshot
    messages = continuation.get("messages")
    if not isinstance(messages, list):
        return snapshot
    slimmed = []
    for element in messages:
        if isinstance(element, dict) and isinstance(element.get("body"), str):
            digest = hashlib.sha256(element["body"].encode("utf-8")).hexdigest()
            bodyless = {key: value for key, value in element.items() if key != "body"}
            slimmed.append({**bodyless, "bodyDigest": digest})
        else:
            slimmed.append(element)
    slim = dict(snapshot)
    slim["executionContinuation"] = {
        **{key: value for key, value in continuation.items() if key != "messages"},
        "messages": slimmed,
    }
    return slim


def build_pinned_trigger_sql(function_name: str = PINNED_FUNCTION_NAME) -> str:
    """The pinned copy of the paperclip trigger function.

    The body is the one of migration 0308 at the commit named in
    `PINNED_TRIGGER_SOURCE`, unchanged. It is installed in `pg_temp`, which
    keeps it out of the database: it lives for this session only and
    disappears with it, so the cleanup leaves nothing behind in the schema.
    """
    return PINNED_TRIGGER_TEMPLATE.replace("{function_name}", function_name)


def build_probe_sql(table: str) -> str:
    """The session-local copy of the runs table that carries the trigger.

    The copy is made with `CREATE TABLE AS`, so it has the columns of the real
    table and none of its constraints: the script fills the snapshot and lets
    the trigger write the mirrored ids.

    The copy carries one column of its own, `original_snapshot`: the value
    the row had when the batch was loaded. The write compares it with the row
    it is about to write, so a row that the instance wrote in the meantime is
    left alone.
    """
    return f"""
CREATE TEMP TABLE IF NOT EXISTS pg_temp.{table} AS
    SELECT * FROM {RUNS_TABLE} WITH NO DATA;
ALTER TABLE pg_temp.{table}
    ADD COLUMN IF NOT EXISTS context_issue_id text,
    ADD COLUMN IF NOT EXISTS context_task_id text,
    ADD COLUMN IF NOT EXISTS original_snapshot jsonb;
""".strip()


def build_probe_trigger_sql(table: str, function_ref: str) -> str:
    """Attach the trigger function to the session-local copy of the table."""
    return f"""
DROP TRIGGER IF EXISTS paperclip_slim_probe_trg ON pg_temp.{table};
CREATE TRIGGER paperclip_slim_probe_trg
    BEFORE INSERT ON pg_temp.{table}
    FOR EACH ROW EXECUTE FUNCTION {function_ref}();
""".strip()



def build_batch_load_sql() -> str:
    """Load one batch into the session-local copy of the runs table.

    The load is a statement of its own, and it has to be. An `UPDATE` that
    reads its new value from a data-modifying CTE runs that CTE again when a
    row of the target table was updated concurrently, and PostgreSQL refuses
    to write inside that re-check: "ModifyTable should not be called during
    EvalPlanQual". The table of a live instance is written while this script
    runs, so that is not a rare thing. A plain load has no such problem: it
    reads the rows under one snapshot and the trigger shapes them.
    """
    return f"""
INSERT INTO pg_temp.{PROBE_TABLE} (id, context_snapshot, original_snapshot)
SELECT id, context_snapshot, context_snapshot
  FROM {RUNS_TABLE}
 WHERE id > %(cursor)s
   AND created_at < %(cutoff)s::timestamptz
 ORDER BY id
 LIMIT %(batch_size)s
""".strip()


def build_batch_update_sql(*, set_id_columns: bool) -> str:
    """The batched, idempotent rewrite of one batch of runs.

    The probe holds the value the trigger computed and the value the row had
    when the batch was loaded. The `IS DISTINCT FROM` guard is what makes the
    cleanup idempotent: a row that is already slim is not written, so it does
    not leave a dead tuple behind either. The second guard skips a row that
    the instance wrote between the load and the write: that row carries a
    fresher snapshot than the batch was built from, and overwriting it would
    lose what the instance wrote.
    """
    set_clause = "context_snapshot = p.context_snapshot"
    if set_id_columns:
        set_clause += (
            ",\n       context_issue_id = p.context_issue_id"
            ",\n       context_task_id = p.context_task_id"
        )
    return f"""
WITH upd AS (
  UPDATE {RUNS_TABLE} AS r
     SET {set_clause}
    FROM pg_temp.{PROBE_TABLE} AS p
   WHERE r.id = p.id
     AND p.context_snapshot IS DISTINCT FROM r.context_snapshot
     AND r.context_snapshot IS NOT DISTINCT FROM p.original_snapshot
  RETURNING r.id
)
SELECT (SELECT count(*) FROM pg_temp.{PROBE_TABLE}) AS scanned,
       (SELECT count(*) FROM upd) AS updated,
       -- `max()` is not defined for uuid, so the cursor is the last id by order
       (SELECT id FROM pg_temp.{PROBE_TABLE} ORDER BY id DESC LIMIT 1) AS last_id
""".strip()


def build_batch_dry_run_sql() -> str:
    """The same batch, counted instead of written."""
    return f"""
SELECT (SELECT count(*) FROM pg_temp.{PROBE_TABLE}) AS scanned,
       count(*) FILTER (
           WHERE p.context_snapshot IS DISTINCT FROM b.context_snapshot
       ) AS updated,
       coalesce(sum(pg_column_size(b.context_snapshot)), 0) AS original_bytes,
       coalesce(sum(pg_column_size(p.context_snapshot)), 0) AS slim_bytes,
       -- `max()` is not defined for uuid, so the cursor is the last id by order
       (SELECT id FROM pg_temp.{PROBE_TABLE} ORDER BY id DESC LIMIT 1) AS last_id
  FROM pg_temp.{PROBE_TABLE} p
  JOIN {RUNS_TABLE} b ON b.id = p.id
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
    secret = env.get(args.password_env, "")
    return conninfo, ({"password": secret} if secret else {})


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


def find_installed_trigger(conn: Any) -> str | None:
    """The qualified name of the trigger function, when the database has it.

    The schema is not guessed, the catalog is asked. The session-local
    schemas are left out, so the pinned copy of this script is never mistaken
    for the trigger of the database.
    """
    with conn.cursor() as cur:
        cur.execute(
            """
            SELECT n.nspname || '.' || p.proname
              FROM pg_proc p
              JOIN pg_namespace n ON n.oid = p.pronamespace
             WHERE p.proname = %(name)s
               AND p.prorettype = 'trigger'::regtype
               AND n.nspname NOT IN ('pg_catalog', 'information_schema')
               AND n.nspname NOT LIKE 'pg_toast%%'
               AND n.nspname NOT LIKE 'pg_temp%%'
             ORDER BY (n.nspname = 'public') DESC, n.nspname
             LIMIT 1
            """,
            {"name": TRIGGER_FUNCTION_NAME},
        )
        row = cur.fetchone()
    return str(row[0]) if row else None


def sample_rows(conn: Any, sample_size: int) -> list[tuple[str, Any]]:
    """Live rows to check the transform on.

    The rows that carry a continuation with messages come first: they are the
    rows the transform does something to. The rest of the sample is filled
    with arbitrary rows, so the check also covers the shapes the transform
    leaves alone.
    """
    rows: list[tuple[str, Any]] = []
    with conn.cursor() as cur:
        cur.execute(
            """
            SELECT id, context_snapshot
              FROM heartbeat_runs
             WHERE context_snapshot IS NOT NULL
               AND jsonb_typeof(context_snapshot -> 'executionContinuation' -> 'messages') = 'array'
             ORDER BY id DESC
             LIMIT %(limit)s
            """,
            {"limit": sample_size},
        )
        rows = [(str(row[0]), row[1]) for row in cur.fetchall()]
        if len(rows) >= sample_size:
            return rows
        bound = uuid.UUID(int=uuid.uuid4().int)
        cur.execute(
            """
            SELECT id, context_snapshot
              FROM heartbeat_runs
             WHERE id >= %(bound)s
               AND context_snapshot IS NOT NULL
             ORDER BY id
             LIMIT %(limit)s
            """,
            {"bound": bound, "limit": sample_size - len(rows)},
        )
        rows += [(str(row[0]), row[1]) for row in cur.fetchall()]
    return rows


def build_trigger_output_sql(table: str) -> str:
    """The value the trigger gives to a set of rows.

    The rows go through the session-local copy of the table that carries the
    trigger, so this is the trigger's own answer and not a copy of it.
    """
    return f"""
WITH sample AS MATERIALIZED (
  SELECT elem ->> 'id' AS id,
         elem -> 'context_snapshot' AS context_snapshot
    FROM jsonb_array_elements(%(rows)s::jsonb) AS elem
), probe AS MATERIALIZED (
  INSERT INTO pg_temp.{table} (id, context_snapshot)
  SELECT id::uuid, context_snapshot FROM sample
  RETURNING id, context_snapshot
)
SELECT s.id,
       s.context_snapshot AS original,
       p.context_snapshot AS transformed
  FROM sample s
  JOIN probe p ON p.id::text = s.id
""".strip()


def trigger_output(conn: Any, table: str, payload: str) -> dict[str, Any]:
    """The transformed snapshot of every row of the payload, keyed by row id."""
    with conn.cursor() as cur:
        cur.execute(build_trigger_output_sql(table), {"rows": payload})
        return {str(row[0]): row[2] for row in cur.fetchall()}


def verify_transform(
    conn: Any, *, sample_size: int, installed_function: str | None
) -> dict[str, Any]:
    """Check the trigger against the Python reference on live rows.

    The trigger is the authority: the script runs it, so a row written here
    and a row written by the database have the same shape. The Python
    reference is the readable copy of it, and the two must agree on every
    sampled row before anything is written. When the database carries the
    trigger, the pinned copy of migration 0308 is compared with it as well, so
    a trigger that moved on without this script is caught here and not on the
    next write.

    A mismatch raises: the cleanup must not run on a transform the script and
    the paperclip trigger disagree about.
    """
    report: dict[str, Any] = {
        "compared": 0,
        "installed_trigger": installed_function,
        "drift_checked": False,
    }
    if sample_size <= 0:
        return report
    rows = sample_rows(conn, sample_size)
    if not rows:
        return report
    payload = json.dumps(
        [{"id": row_id, "context_snapshot": snapshot} for row_id, snapshot in rows],
        default=str,
    )
    produced = trigger_output(conn, PROBE_TABLE, payload)
    compared = 0
    for row_id, original in rows:
        expected = slim_snapshot(original)
        transformed = produced.get(row_id)
        if transformed is None:
            raise RuntimeError(
                f"the trigger produced no value for row {row_id}; refusing to write"
            )
        if expected != transformed:
            raise RuntimeError(
                f"the trigger and the Python reference disagree on row {row_id}; "
                "refusing to write"
            )
        compared += 1
    report["compared"] = compared

    if installed_function is not None:
        pinned = trigger_output(conn, DRIFT_PROBE_TABLE, payload)
        for row_id, _original in rows:
            if pinned.get(row_id) != produced.get(row_id):
                raise RuntimeError(
                    "the installed trigger and the pinned copy of migration 0308 "
                    f"disagree on row {row_id}; refusing to write"
                )
        report["drift_checked"] = True
    return report


def run_cleanup(
    conn: Any,
    *,
    load_sql: str,
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
        batch_scanned = 0
        batch_updated = 0
        last_id = None
        # A live table is written while this script runs, and PostgreSQL
        # answers a write that ran into a concurrent change with a retryable
        # error. The batch is safe to run again: it only writes rows whose
        # value the trigger computed and whose value the instance has not
        # touched since the batch was loaded.
        for attempt in range(1, BATCH_ATTEMPTS + 1):
            try:
                with conn.cursor() as cur:
                    # The probe holds one batch. It is emptied first, so a
                    # batch that is run again does not count its rows twice.
                    cur.execute(f"TRUNCATE pg_temp.{PROBE_TABLE}")
                    cur.execute(load_sql, params)
                    if dry_run:
                        cur.execute(dry_run_sql)
                        row = cur.fetchone()
                        batch_scanned = int(row[0])
                        batch_updated = int(row[1])
                        original_bytes += int(row[2])
                        slim_bytes += int(row[3])
                        last_id = row[4]
                    else:
                        cur.execute(update_sql)
                        row = cur.fetchone()
                        batch_scanned = int(row[0])
                        batch_updated = int(row[1])
                        last_id = row[2]
                break
            except Exception as exc:
                # The error is re-raised unless it is one of the retryable
                # SQLSTATEs, so a real failure is never swallowed.
                sqlstate = getattr(exc, "sqlstate", None)
                if attempt >= BATCH_ATTEMPTS or sqlstate not in RETRYABLE_SQLSTATES:
                    raise
                print(
                    f"  batch {batches + 1}: {exc}; retrying ({attempt}/{BATCH_ATTEMPTS})",
                    flush=True,
                )
                time.sleep(1.0)
        # The probe holds the transformed rows of the batch. It is emptied
        # here, so the session does not keep a copy of every row it touched.
        with conn.cursor() as cur:
            cur.execute(f"TRUNCATE pg_temp.{PROBE_TABLE}")
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
    parser.add_argument("--dry-run", action="store_true", help="count, do not write")
    parser.add_argument(
        "--verify-sample",
        type=int,
        default=25,
        help="live rows to check the trigger against the Python reference on before "
        "writing (0 skips the check)",
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
    print("  transform: the paperclip trigger, run on a copy of the table")
    if args.dry_run:
        print("  mode: dry run, nothing is written")

    try:
        with psycopg.connect(conninfo, autocommit=True, **connect_kwargs) as conn:
            with conn.cursor() as cur:
                cur.execute(f"SET statement_timeout = '{args.statement_timeout_ms}ms'")
                # The pinned copy of the migration function lives in the session
                # only. It is the writer when the database does not carry the
                # trigger yet, and it is the reference the installed trigger is
                # compared against.
                cur.execute(build_pinned_trigger_sql())
                cur.execute(build_probe_sql(PROBE_TABLE))
                cur.execute(build_probe_sql(DRIFT_PROBE_TABLE))

            installed = find_installed_trigger(conn)
            active_function = installed or f"pg_temp.{PINNED_FUNCTION_NAME}"
            with conn.cursor() as cur:
                cur.execute(build_probe_trigger_sql(PROBE_TABLE, active_function))
                cur.execute(
                    build_probe_trigger_sql(DRIFT_PROBE_TABLE, f"pg_temp.{PINNED_FUNCTION_NAME}")
                )

            if installed:
                print(f"  trigger: {installed}, the installed trigger shapes the rows")
            else:
                print(
                    "  trigger: not installed in this database, using the pinned copy of "
                    f"{PINNED_TRIGGER_SOURCE}"
                )

            verification = verify_transform(
                conn, sample_size=args.verify_sample, installed_function=installed
            )
            drift_note = (
                ", and the pinned copy against the installed trigger"
                if verification["drift_checked"]
                else ""
            )
            print(
                "  verified the trigger against the Python reference on "
                f"{verification['compared']} rows{drift_note}"
            )
            with conn.cursor() as cur:
                cur.execute(f"TRUNCATE pg_temp.{PROBE_TABLE}")
                cur.execute(f"TRUNCATE pg_temp.{DRIFT_PROBE_TABLE}")

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
                load_sql=build_batch_load_sql(),
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
                "older_than_days": args.older_than_days,
                "batch_size": args.batch_size,
                "trigger": {
                    "installed": verification["installed_trigger"],
                    "pinned_source": PINNED_TRIGGER_SOURCE,
                    "verified_rows": verification["compared"],
                    "drift_checked": verification["drift_checked"],
                },
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
