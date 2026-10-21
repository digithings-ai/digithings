# heartbeat_runs and heartbeat_run_events: retention policy (DIG-4821)

What to keep, for how long, how to delete it in batches, and when the
deletions may run. This is the standing policy for the two tables that
record what a heartbeat run did. It covers the **local embedded Paperclip
instance** (`127.0.0.1:54329`) and the shape the same tables have in the
managed instance.

## Why the policy exists

`heartbeat_runs.context_snapshot` is a **render cache**: the issue body, the
comments and the task assignment are stored again, in rendered markdown, in
every run row. On 2026-10-21 the table held 28.5k rows and 2.7 GiB, of which
**2.6 GiB was TOAST** — the fat payload. The attention feed then reads
`context_snapshot->>'issueId'` and `->>'taskId'` per row, so every scheduler
tick detoasted the whole column:

```
Seq Scan on heartbeat_runs  (actual time 0.680..5621.584 ms, rows=26351)
Buffers: shared hit=293989 read=126327 written=155   (~420k buffers, 3.36 GB)
```

The one-off cleanup in `scripts/paperclip_heartbeat_runs_slim.py` (DIG-4821)
slims the existing rows, and the write-time trigger (DIG-4762, paperclip
migration `0308_heartbeat_run_context_columns.sql`) keeps new rows slim. This
document is the part that stops the table growing back: **what to delete,
after how long, in batches of what size, and in which window.**

## What the cleanup measured (2026-10-21, local instance)

| measurement | before | after |
|---|---|---|
| `heartbeat_runs` TOAST on disk | 2,794,856,448 B (2.60 GiB) | 2,252,054,528 B (2.10 GiB) |
| `heartbeat_runs` total on disk | 2,907,250,688 B (2.71 GiB) | 2,337,923,072 B (2.18 GiB) |
| live `context_snapshot` payload | 904,746,235 B (862.8 MiB) | 445,886,153 B (425.2 MiB) |
| average `pg_column_size(context_snapshot)` | 31,665 B | 15,604 B |
| scheduler query, buffers touched | 420,301 (3.36 GB) | 297,443 (2.38 GB) |
| scheduler query, execution time | 5.6–11.0 s | 2.2–9.4 s |

28,572 rows were scanned, 23,641 rewritten (83%); a second pass rewrote **0**
rows, which is the idempotency proof on live data. The plan **shape did not
change** — still a Seq Scan, because the planner does not model the cost of
detoasting a TOASTed value. The plan shape is fixed by DIG-4762, which puts
the issue and task ids in real columns that can be index-scanned; the
cleanup only makes the rows the scheduler reads smaller.

The wall-clock times are noisy on this instance because Paperclip's own
scheduler queries run against the same table at the same time. The **buffer
count** is the stable number: 420,301 → 297,443, a 29% reduction in the I/O
one scheduler tick costs.

### What is still in the table

After the cleanup the TOAST of `heartbeat_runs` is 2.10 GiB, and the snapshot
is only a fifth of it:

| column | TOAST bytes | share |
|---|---|---|
| `result_json` (mostly `result_json->'stdout'`) | 1,407 MB | 65% |
| `context_snapshot` | 445 MB | 20% |
| `stdout_excerpt` | 159 MB | 7% |
| `usage_json` | 28 MB | 1% |

`result_json` holds the run's stdout: 3.4 GB of text across 25,060 rows,
stored compressed into 1.4 GB, with a maximum of 4.1 MB in a single row. That
is a **bigger lever than the snapshot** and a different decision — how long a
run keeps its own output, and whether the external log store
(`log_store`, `log_ref`, `log_sha256`) is the copy that matters. That decision
belongs to the parent issue (DIG-4762), not to this cleanup, so this policy
keeps the stdout inside the retention window and says so instead of quietly
dropping it.

## The policy

| table | keep | age measured on | batch size | window | method |
|---|---|---|---|---|---|
| `heartbeat_run_events` | 14 days | `created_at` | 5,000 rows per transaction | nightly, 03:00–05:00 Europe/Rome | plain `DELETE`, autovacuum reclaims |
| `heartbeat_runs` | 30 days | `coalesce(finished_at, created_at)` | 500 rows per transaction | nightly, 03:00–05:00 Europe/Rome, after the events pass | plain `DELETE`, autovacuum reclaims |

The stdout inside `result_json` (65% of the remaining TOAST) has the same
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
- **The window is a window.** The deletions run between 03:00 and 05:00
  Europe/Rome, when no operator and no board session is on the instance.
  Outside the window the tables are read-only for this job.
- **Plain `DELETE` + autovacuum is the default.** It returns the space to the
  free space map for reuse. `VACUUM FULL` is an operator action, not part of
  the job (see below).

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
  session points somewhere else or the session is deleted too. The job
  therefore re-points `last_run_id` to the newest surviving run of the same
  session before deleting the old one.
- **`cost_events` and `finance_events`** are the money trail. They are not
  deleted by this job — a run with cost or finance rows is **skipped** and
  reported, because the ledger outlives the run. The run then stays until the
  ledger is archived separately.

## The SQL the job runs

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
fail: a run with money attached is left in place and counted in the run
report.

## Vacuum: plain by default, `VACUUM FULL` by hand

- **Plain `VACUUM (ANALYZE)`** returns the dead tuples to the free space map.
  The files do not shrink, but later inserts reuse the space and the table
  stops growing. This is the default and it is enough.
- **`VACUUM FULL`** rewrites the table and its TOAST and gives the bytes back
  to the filesystem. It takes an **ACCESS EXCLUSIVE** lock for the whole
  rewrite — on a 2.7 GiB table that is minutes of blocked reads for the
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
- **The renders.** The markdown copies are dropped from the snapshot at write
  time by the trigger (DIG-4762). Old rows are slimmed once by the script in
  this repository; the trigger does not retroactively touch them.
- **The backlog.** A run blocked by the ledger stays until the ledger is
  archived. The job report counts the skipped runs so the backlog is visible
  instead of silent.

## The report

Every run of the job ends with the numbers that decide whether the policy is
working: rows deleted per table, rows skipped and why, free space map size,
and the size of both tables before and after. The one-off cleanup writes the
same report as JSON (`--json-out`).
