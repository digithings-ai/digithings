# heartbeat_runs and heartbeat_run_events: retention policy (DIG-4821)

What to keep, for how long, how to delete it in batches, and when the
deletions may run. This is the standing policy for the two tables that
record what a heartbeat run did. It covers the **local embedded Paperclip
instance** (`127.0.0.1:54329`) and the shape the same tables have in the
managed instance.

## How the deletions are run

**By hand, inside the window. There is no scheduled job for this.** Nothing
in this repository deletes these tables on a timer: the only tracked files
that name `heartbeat_run_events` are this document and the one-off cleanup
script `scripts/paperclip_heartbeat_runs_slim.py`, and neither schedules
anything. An operator runs the SQL in this document by hand, in the
maintenance window, and records the numbers at the end (see *The report*).

A scheduled job, when one is ever written, is a behaviour change against
`heartbeat_runs`. It lands as its own PR with its own review, not inside this
policy.

## Why the policy exists

`heartbeat_runs.context_snapshot` is a **render cache**: the issue body, the
comments and the task assignment are stored again, in rendered markdown, in
every run row, together with the wake payload of the run.

The write-time trigger (DIG-4762, paperclip migration
`0308_heartbeat_run_context_columns.sql`) **keeps** all of it. The external
chat contract reads the issue work mode, the continuation summary and the
rendered wake comments back out of the stored snapshot, so the trigger takes
one thing out of it and nothing else: the body of every comment of the
top-level `executionContinuation` is replaced by a SHA-256 `bodyDigest`.

The snapshot stays big on purpose. What keeps the table bounded is **how long
the rows are kept**, not how thin the snapshot is. That is what this document
is for. On 2026-10-22 the table held 29.3k rows and 2.96 GiB, of which
**2.84 GiB was TOAST**, and the attention feed reads
`context_snapshot->>'issueId'` and `->>'taskId'` per row, so every scheduler
tick detoasted the whole column:

```
Seq Scan on heartbeat_runs  (actual time 0.043..3939.380 ms, rows=26908)
Buffers: shared hit=259291 read=46993 written=68   (~306k buffers, 2.4 GB)
```

After the cleanup and the compaction the same table holds 2.17 GiB, of which
2.09 GiB is TOAST, and one tick touches about 270k buffers.

The one-off cleanup in `scripts/paperclip_heartbeat_runs_slim.py` (DIG-4821)
gives the rows that already exist the same shape the trigger gives the new
ones. This document is the part that stops the table growing back: **what to
delete, after how long, in batches of what size, and in which window.**

## What the cleanup does

The cleanup does not implement the trigger a second time: **it runs the
trigger.** It copies `heartbeat_runs` into a session-local table
(`pg_temp.paperclip_slim_probe`), attaches the trigger function to that copy,
and lets the trigger compute the new value of every snapshot. A row written by
the script and a row written by the database therefore have the same shape,
because it is the same function that shaped them.

Two checks run before the first write:

- The answer of the trigger is compared with a readable Python copy of the
  same shape, on live rows. A disagreement stops the run.
- When the database carries the trigger, the pinned copy of migration 0308 is
  compared with the installed function on the same rows, so a trigger that
  moved on without this script is caught here and not on the next write.

The rows are rewritten in batches, one transaction per batch, and a row whose
snapshot is already slim is not written at all: a second run rewrites nothing.

**The cleanup cannot undo an older, more aggressive cleanup.** The first run
of this script (2026-10-21) applied a transform that removed the rendered
prompt copies and the wake copies from the snapshot. The trigger that shipped
afterwards keeps them, and no script can put back what was removed. Those
rows keep the thin shape they were given; the new rows carry the full shape.

## What the cleanup measured

### 2026-10-22, the run that matches the trigger

Measured on the local instance (127.0.0.1:54329, PostgreSQL 18.1) with the
script in this repository, `--batch-size 500`.

| measurement | before | after |
|---|---|---|
| `heartbeat_runs` TOAST on disk | 3,046,424,576 B (2.84 GiB) | 3,049,119,744 B (2.84 GiB) |
| `heartbeat_runs` total on disk | 3,150,217,216 B (2.93 GiB) | 3,180,888,064 B (2.96 GiB) |
| live `context_snapshot` payload | 458,658,013 B (437.4 MiB) | 311,003,390 B (296.6 MiB) |
| average `pg_column_size(context_snapshot)` | 15,711 B | 10,652 B |
| max `pg_column_size(context_snapshot)` | 406,095 B | 352,592 B |
| scheduler query, buffers touched | 306,352 | 274,322 |
| scheduler query, execution time | 3.94 s | 1.41 s |

**29,195 rows were scanned, 15,004 rewritten (51%)**, in 60 batches of 500.
The TOAST on disk did not shrink in the rewrite: the old chunks stay in the
relation as dead tuples, and only the compaction gives the space back (see
*Vacuum: plain by default, VACUUM FULL by hand*).

### 2026-10-22, the compaction and the final pass

The compaction ran in the window, by hand, with the same guard the runbook
prescribes (`SET lock_timeout = '5s'` before `VACUUM FULL heartbeat_runs`):

| measurement | before | after |
|---|---|---|
| `heartbeat_runs` TOAST on disk | 3,049,168,896 B (2.84 GiB) | 2,243,657,728 B (2.09 GiB) |
| `heartbeat_runs` total on disk | 3,181,035,520 B (2.96 GiB) | 2,331,541,504 B (2.17 GiB) |
| whole database on disk | 5,796,189,887 B | 4,947,482,303 B |
| scheduler query, buffers touched | 274,896 | 269,695 |

**805,511,168 B (768 MiB) of TOAST and 848,707,584 B (809 MiB) of database
came back to the filesystem.** The plan shape did not change and the wall
clock did not move (1.87 s before, 1.95 s after — the scheduler's own queries
run against the same table at the same time). The compaction removes dead
tuples; it does not make the rows smaller, and it does not change the plan.

The cleanup pass that ran with the compaction **rewrote 0 of 29,282 rows**:
the trigger's shape was already on every row, which is the idempotency proof
on live data. The 35 rows that still needed it were the ones the instance had
written between the two passes; a third pass, immediately after, rewrote
nothing at all.

| pass | rows scanned | rows rewritten |
|---|---|---|
| 2026-10-22, first pass | 29,195 | 15,004 |
| 2026-10-22, pass after the compaction | 29,281 | 35 |
| 2026-10-22, pass with the compaction | 29,282 | 0 |

The scheduler query, the same shape as the attention feed
(`context_snapshot->>'issueId'`, `->>'taskId'`, `company_id = $1`,
`agent_id in (...)`, `created_at > $2`), measured before and after in the same
run:

```
before  Seq Scan on heartbeat_runs  (actual time=0.043..3939.380 ms, rows=26908)
        Buffers: shared hit=259291 read=46993 written=68
        Execution Time: 3941.694 ms

after   Seq Scan on heartbeat_runs  (actual time=0.066..1413.059 ms, rows=26911)
        Buffers: shared hit=246716 read=27336 dirtied=50 written=220
        Execution Time: 1414.036 ms
```

The **plan shape did not change** — still a Seq Scan, because the planner does
not model the cost of detoasting a TOASTed value. The plan shape is fixed by
DIG-4762, which puts the issue and task ids in real columns that can be
index-scanned; the cleanup only makes the rows the scheduler reads smaller.
The wall-clock times are noisy on this instance because Paperclip's own
scheduler queries run against the same table at the same time. The **buffer
count** is the stable number: 306,352 → 274,322, a 10% reduction in the I/O
one scheduler tick costs.

### 2026-10-21, the first run, and the transform it used

The first run of the script applied a transform that removed the rendered
prompt copies and the wake copies from the snapshot. It was measured at the
time:

| measurement | before | after |
|---|---|---|
| `heartbeat_runs` TOAST on disk | 2,794,856,448 B (2.60 GiB) | 2,252,054,528 B (2.10 GiB) |
| `heartbeat_runs` total on disk | 2,907,250,688 B (2.71 GiB) | 2,337,923,072 B (2.18 GiB) |
| live `context_snapshot` payload | 904,746,235 B (862.8 MiB) | 445,886,153 B (425.2 MiB) |
| average `pg_column_size(context_snapshot)` | 31,665 B | 15,604 B |
| scheduler query, buffers touched | 420,301 (3.36 GB) | 297,443 (2.38 GB) |
| scheduler query, execution time | 5.6–11.0 s | 2.2–9.4 s |

28,572 rows were scanned and 23,641 rewritten (83%); a second pass rewrote
**0** rows, which is the idempotency proof on live data.

**That transform is not the trigger's transform, and it is not what the script
does now.** The trigger keeps the rendered prompt and the wake payload,
because the production read paths need them. The rows that run touched keep
the thin shape it gave them — no script can put the removed keys back — while
the rows written since keep the full shape. The 2026-10-22 run gave the rows
the trigger's shape.

## What is still in the table

After the compaction the TOAST of `heartbeat_runs` is 2.09 GiB, and the
snapshot is a seventh of it:

| column | bytes on disk | share of the four |
|---|---|---|
| `result_json` (mostly `result_json->'stdout'`) | 1,593,989,091 B (1.48 GiB) | 76% |
| `context_snapshot` | 313,020,723 B (298.5 MiB) | 15% |
| `stdout_excerpt` | 172,262,174 B (164.3 MiB) | 8% |
| `usage_json` | 29,831,472 B (28.4 MiB) | 1% |

`result_json` holds the run's stdout: 3,895,931,528 B (3.63 GB) of text
across 25,460 rows, stored compressed into 1.48 GiB, with a maximum of
4,194,304 B (4.0 MiB) in a single row. That is a **bigger lever than the
snapshot** and a different decision — how long a run keeps its own output,
and whether the external log store (`log_store`, `log_ref`, `log_sha256`) is
the copy that matters. That decision belongs to the parent issue (DIG-4762),
not to this cleanup, so this policy keeps the stdout inside the retention
window and says so instead of quietly dropping it.

## The policy

| table | keep | age measured on | batch size | window | method |
|---|---|---|---|---|---|
| `heartbeat_run_events` | 14 days | `created_at` | 5,000 rows per transaction | by hand, 03:00–05:00 Europe/Rome | plain `DELETE`, autovacuum reclaims |
| `heartbeat_runs` | 30 days | `coalesce(finished_at, created_at)` | 500 rows per transaction | by hand, 03:00–05:00 Europe/Rome, after the events pass | plain `DELETE`, autovacuum reclaims |

Two batch sizes appear in this document and they are not the same number:

- **500 rows per transaction** is the batch of the retention `DELETE` in the
  SQL below.
- **200 rows per transaction** is the default of the one-off cleanup script
  (`--batch-size`). The measured runs used `--batch-size 500`: the 2026-10-21
  run reports 59 batches for the 28,572 rows it scanned, and the 2026-10-22
  run reports 60 batches for the 29,195 rows it scanned.

The stdout inside `result_json` (76% of the remaining TOAST) has the same
30-day life as the run it belongs to. It is **not** dropped separately: the
question "does a run keep its own output for 30 days, or does the external
log store own it" is a product decision that belongs to DIG-4762, and until
it is made the retention window keeps the output whole.

Rules that go with the numbers:

- **Only terminal runs are deleted.** `status in ('succeeded', 'failed',
  'cancelled', 'interrupted')`. A `queued` or `running` row is never a
  retention candidate, whatever its age.
- **The batch size is a transaction, not a statement.** Each batch commits on
  its own, so a failed batch loses one batch and the next run resumes.
  PostgreSQL has no `DELETE ... LIMIT`, so the batch is a CTE (below).
- **The window is a window.** The procedure runs between 03:00 and 05:00
  Europe/Rome, when no operator and no board session is on the instance.
  Outside the window the tables are not touched by this procedure: it is run
  by hand, and the window is when the instance is quiet enough for it.
- **Plain `DELETE` + autovacuum is the default.** It returns the space to the
  free space map for reuse. `VACUUM FULL` is a separate operator action, not
  part of this procedure (see below).

## The order of deletion: the foreign keys decide it

A plain `DELETE FROM heartbeat_runs` **fails**. Sixteen child tables hold a
`NO ACTION` foreign key on `heartbeat_runs`, so PostgreSQL refuses to delete a
run while a child row points at it:

| child table | column |
|---|---|
| `activity_log` | `run_id` |
| `agent_task_sessions` | `last_run_id` |
| `browser_use_runs` | `heartbeat_run_id` |
| `cost_events` | `heartbeat_run_id` |
| `decision_bundles` | `origin_run_id` |
| `decision_queue_items` | `added_by_run_id` |
| `decision_queues` | `created_by_run_id` |
| `decision_retention` | `archived_by_run_id` |
| `decision_triage` | `set_by_run_id` |
| `decision_triage_events` | `actor_run_id` |
| `decisions` | `origin_run_id` |
| `finance_events` | `heartbeat_run_id` |
| `heartbeat_run_events` | `run_id` |
| `native_run_finalizations` | `run_id` (plus the composite `run_owner_fk`) |
| `native_run_results` | `run_id` (plus the composite `run_contract_owner_fk`) |
| `work_assessments` | `run_id` (plus the composite `run_owner_fk`) |

The other references are harmless: `CASCADE` tables
(`heartbeat_run_watchdog_decisions`, `tool_gateway_sessions`,
`company_secret_proposals`, `provider_trace_records`,
`agent_instruction_working_copies`, `permission_grant_proposals`) go with the
run, and `SET NULL` tables (issue comments, issues, tool invocations, chat
completion deliveries, …) keep their rows and point at nothing.

Two traps in that table:

- **`agent_task_sessions.last_run_id`** is a pointer, not ownership. A run
  that is the *last* run of a task session blocks the delete until the
  session points somewhere else or the session is deleted too. The procedure
  therefore re-points `last_run_id` to the newest surviving run of the same
  session before deleting the old one.
- **`cost_events` and `finance_events`** are the money trail. They are not
  deleted by this procedure — a run with cost or finance rows is **skipped**
  and reported, because the ledger outlives the run. The run then stays until
  the ledger is archived separately.

## The SQL the procedure runs

Run these statements by hand, in this order, inside the window. Each one is
its own transaction.

```sql
-- 1. events first: nothing points at an event, so they go in any order
WITH doomed AS (
  SELECT id
    FROM heartbeat_run_events
   WHERE created_at < now() - interval '14 days'
   ORDER BY id
   LIMIT 5000
)
DELETE FROM heartbeat_run_events e USING doomed d WHERE e.id = d.id;

-- 2. the per-run children that block a delete of the run
--    doomed_runs = the set of runs selected in step 3 (materialise it
--    first: the CTE of step 3 is scoped to that statement)
DELETE FROM native_run_results
 WHERE run_id IN (SELECT id FROM doomed_runs);
--    ... the same for native_run_finalizations, work_assessments,
--    browser_use_runs, activity_log, decision_*, agent_task_sessions

-- 3. the runs themselves, terminal states only, 500 at a time
WITH doomed AS (
  SELECT id
    FROM heartbeat_runs
   WHERE coalesce(finished_at, created_at) < now() - interval '30 days'
     AND status IN ('succeeded', 'failed', 'cancelled', 'interrupted')
     AND NOT EXISTS (SELECT 1 FROM cost_events c WHERE c.heartbeat_run_id = heartbeat_runs.id)
     AND NOT EXISTS (SELECT 1 FROM finance_events f WHERE f.heartbeat_run_id = heartbeat_runs.id)
   ORDER BY id
   LIMIT 500
)
DELETE FROM heartbeat_runs r USING doomed d WHERE r.id = d.id;
```

`NOT EXISTS` on the ledger tables is what makes the run batch skip instead of
fail: a run with money attached is left in place and counted in the report.

## Vacuum: plain by default, `VACUUM FULL` by hand

- **Plain `VACUUM (ANALYZE)`** returns the dead tuples to the free space map.
  The files do not shrink, but later inserts reuse the space and the table
  stops growing. This is the default and it is enough.
- **`VACUUM FULL`** rewrites the table and its TOAST and gives the bytes back
  to the filesystem. It takes an **ACCESS EXCLUSIVE** lock for the whole
  rewrite — on a table of this size (2.96 GiB before the 2026-10-22
  compaction, 2.17 GiB after) that is minutes of blocked reads for the
  scheduler. It is an operator action, inside the 03:00–05:00 window, with a
  lock timeout so it gives up instead of queueing behind a long transaction:

```sql
SET lock_timeout = '5s';
VACUUM (FULL, ANALYZE) heartbeat_runs;
```

  If the lock is not free within 5 s the statement fails and the window is
  rescheduled. Never run `VACUUM FULL` from a migration: the migration runner
  uses `--single-transaction`.

The one-off cleanup in `scripts/paperclip_heartbeat_runs_slim.py` follows the
same rule: `--vacuum` is plain, `--vacuum-full` is guarded by
`--lock-timeout-ms` and is only used deliberately.

## What the policy does not cover

- **The snapshot of a live run.** A run that is `queued` or `running` is never
  deleted, whatever its age.
- **The ledger.** `cost_events` and `finance_events` have their own
  retention, set by finance, not by this policy.
- **The renders.** The trigger **keeps** the rendered prompt copies and the
  wake payload in the snapshot, on purpose: the production read paths need
  them (the issue work mode, the continuation summary and the rendered wake
  comments are read back out of the stored snapshot). The cleanup does not
  touch them either. The one thing the trigger takes out of the snapshot is
  the body of every comment of the top-level `executionContinuation`, and the
  cleanup replaces those bodies with the same digest the trigger writes.
  The rows of the first cleanup run (2026-10-21) are the exception: that run
  used a more aggressive transform and removed the renders from them. No
  script can put them back.
- **The backlog.** A run blocked by the ledger stays until the ledger is
  archived. The report counts the skipped runs so the backlog is visible
  instead of silent.

## Scrubbing bearer values from result_json (DIG-5228)

A run result carries the agent's own run token in the text of its `stdout`,
and the token was stored as it was printed: `heartbeat_runs.result_json`
held the value in the clear, in rows written before the server learned to
redact it. The value is a credential, so it has to be taken out of the rows
that already exist.

The scrub lives in `scripts/paperclip_heartbeat_runs_redact_secrets.py`,
in the style of `scripts/paperclip_heartbeat_runs_slim.py`:

- One transaction per batch; a row with no bearer value is not written, so a
  second run rewrites nothing.
- A `--dry-run` that writes nothing.
- The database password comes from an environment variable
  (`PGPASSWORD` or `PAPERCLIP_DATABASE_URL`), never a command line argument.
- No `VACUUM FULL`; a plain `VACUUM (ANALYZE)` is enough (`--vacuum`).

The rule is not written in this repository. The Paperclip server owns it:
`redactEventPayload` from `server/src/redaction.ts` in the
`digithings-ai/paperclip` checkout (the helper the server already runs on
the run event write path, and the one DIG-5227 puts on the run result write
path). The script bundles that module out of the checkout with the
checkout's own esbuild and runs it against the live rows, so the value it
stores is the value the server itself would have stored. A pinned Python copy
of the server's bearer detector (`looks_like_credential_jwt`) decides which
rows hold a bearer value and whether the server's rule and the pinned copy
agree; the two are compared before anything is written — once on a synthetic
fixture, once on a sample of the live rows — and the script refuses to write
when they disagree.

The values are found by shape and never by matching a known one, and they
are never printed: not on stdout, not in the report, not in an error message.
The report carries counts only: rows scanned, rows rewritten, values found,
how many were still inside their own TTL (read from the `exp` claim, never
printed). `kit/bin/dt-secret-scan` runs clean on the files it touches.

The scrub is idempotent: a second run reports zero rewritten rows and the
post-scan finds no bearer-shaped value left in `result_json`.

## The report


**No job writes this report: the operator records it.** At the end of the
procedure, write down the numbers that decide whether the policy is working:
rows deleted per table, rows skipped and why, free space map size, and the
size of both tables before and after. The one-off cleanup script writes the
same report as JSON (`--json-out`).
