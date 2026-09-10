# Checkpoint archive: VACUUM strategy + size relief measurement (#3811)

How NULL-ing archived checkpoint/document payloads turns into real,
reusable DB space — and how to verify it. Read-only; nothing here writes
to prod.

## Background

`pipeline-checkpoint-archive.yml` (13:30 UTC daily) offloads finished
threads' `bytea` payloads to R2 and NULLs the cells
(`digiquant/src/digiquant/ops/checkpoint_archive.py`: `archive_thread`,
`archive_documents`). NULL-ing creates **dead tuples** — `pg_database_size`
does not drop until those tuples are vacuumed. The "588MB → ~488MB" math
in the archive design spec is therefore **unverified until measured
pre/post with the queries below**.

## VACUUM strategy

No new VACUUM job is needed. Two existing mechanisms cover the archive
path; this was verified, not assumed:

1. **pg_cron `langgraph-checkpoint-vacuum`** (migration `061`, daily
   `50 5 * * *` UTC): plain `VACUUM (ANALYZE)` over `checkpoints`,
   `checkpoint_writes`, `checkpoint_blobs`. The archive runs at 13:30 UTC,
   *after* the vacuum — so one archive's dead tuples wait for the **next
   morning's 05:50 run**. Expect size relief to land ~16h after the
   archive, not same-day.
2. **Autovacuum** covers everything else, including `documents` (whose
   payload NULLs are *not* in the 061 vacuum list) and `archive_objects`
   ledger churn.

Rules (from 061, repeated here so operators don't re-decide them):

- **Never `VACUUM FULL`** — ACCESS EXCLUSIVE lock blocks the pipeline for
  zero benefit on these insert-mostly tables.
- Plain `VACUUM` returns space to the **free-space map for reuse**, not to
  the OS — `pg_database_size` may stay flat while per-table
  `pg_total_relation_size` falls and later inserts stop growing the DB.
  Growth capped is the win; bytes-back-from-OS is not promised.
- VACUUM must never appear in a migration body (`db-migrate.yml` uses
  `--single-transaction`; see `tests/dq/research/test_migration_061.py`).

## Measuring pre/post (read-only)

Run before the 13:30 archive and again after the next 05:50 vacuum
(both via the read-only Postgres URI; never the service key path):

```sql
-- Per-table footprint (the number that should fall):
SELECT relname AS table_name,
       pg_size_pretty(pg_total_relation_size('public.' || relname)) AS total_size
  FROM (VALUES ('checkpoints'), ('checkpoint_writes'),
               ('checkpoint_blobs'), ('documents'),
               ('archive_objects')) AS t(relname));

-- Whole-DB size (may stay flat — see FSM note above):
SELECT pg_size_pretty(pg_database_size(current_database())) AS db_size;

-- Dead-tuple pressure (falls to ~0 after the vacuum):
SELECT relname, n_live_tup, n_dead_tup, last_vacuum, last_autovacuum
  FROM pg_stat_user_tables
 WHERE relname IN ('checkpoints', 'checkpoint_writes',
                   'checkpoint_blobs', 'documents')
 ORDER BY relname;
```

Record the three outputs; the gate below automates the first two.

## Workflow size gate (advisory)

`pipeline-checkpoint-archive.yml` ends with a **size-gate step**
(`scripts/digiquant_checkpoint_size_gate.py`). It is deliberately
**advisory, not blocking**: `continue-on-error: true`, and the script
itself exits 0 on DB errors unless `--strict` is passed. A red gate
never fails the archive — it pages the operator via the failed-step
annotation.

- Default threshold: `--threshold-mb 500` (free-tier quota).
- Override per-run via the `threshold-mb` dispatch input if the quota changes.
- `--strict` exists for one-shot operator verification runs, not for
  the scheduled path.

## What "relief verified" looks like

1. Pre-archive per-table sizes recorded.
2. Archive manifest uploaded (existing artifact step).
3. Next-morning `n_dead_tup ≈ 0` on the three checkpoint tables and
   per-table `pg_total_relation_size` down by roughly the archived
   payload bytes (zstd-compressed sizes are in the manifest).
4. `pg_database_size` flat-or-down (flat is fine — FSM reuse).
