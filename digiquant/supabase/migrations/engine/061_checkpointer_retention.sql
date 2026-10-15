-- 061_checkpointer_retention.sql — bound LangGraph checkpointer growth (#1758).
--
-- Run with:  supabase db push   (or, on prod, automatically by db-migrate.yml on
-- push to main). This migration is purely STRUCTURAL: it installs the prune
-- function and two pg_cron jobs. It deletes NOTHING at apply time — the first
-- scheduled fire does the work, so a replay is a true no-op and a bug in the
-- function surfaces as a `cron.job_run_details` row rather than a failed
-- promotion.
--
-- WHY ---------------------------------------------------------------------
-- The Postgres checkpointer (#665, DIGI_CHECKPOINTER=postgres) was enabled with
-- RLS only (migration 036) and no retention companion. LangGraph never prunes
-- thread state itself, and `thread_id` is `"<GITHUB_RUN_ID>::atlas"` /
-- `"::hermes"` (hermes/chain.py:125) — never reused — so rows accumulate
-- monotonically. Measured 2026-08-01: checkpoint_blobs 480 MB +
-- checkpoint_writes 470 MB + checkpoints 2704 kB = 952 MB of a 1263 MB
-- database (75%), 1486 checkpoint rows across 97 threads, and `cron.job` holds
-- only the two prices-live entries. Growth stepped 6.6x on 2026-07-21
-- (8.8 -> ~50-58 MB/day), which is ~4-5 months of runway to an 8 GB ceiling.
--
-- User ruling (D6, 2026-08-01): retain **14 days**.
--
-- WHAT THIS IS HONESTLY WORTH ---------------------------------------------
-- At 14 days, 61 of 97 threads are eligible today: 949 `checkpoints` rows,
-- 7491 `checkpoint_writes`, 2113 `checkpoint_blobs` = ~215 MB compressed
-- (110 MB blobs + 105 MB writes, by sum(pg_column_size(row))) of the 952 MB.
-- Steady state lands near 700-800 MB. `pg_database_size` will NOT drop by
-- 215 MB: plain VACUUM returns space to the free space map for reuse by later
-- inserts, not to the operating system. **The value of this migration is
-- capping growth, not reclaiming disk.** The 94% root cause — 52 full
-- `AtlasResearchState` copies per H5/H6 fan-out superstep on the
-- `__pregel_tasks` channel, which violates digigraph/AGENTS.md "State stays
-- lean" — is a separate, deferred change (see #1758's follow-up); retention
-- caps the footprint but does not reduce the ~48 MB/day of write volume.
--
-- WHAT GETS DELETED, AND WHEN ---------------------------------------------
--   05:20 UTC daily  `langgraph-checkpoint-prune`   — every row of all three
--                    checkpointer tables belonging to a thread whose NEWEST
--                    checkpoint is older than 14 days.
--   05:50 UTC daily  `langgraph-checkpoint-vacuum`  — plain VACUUM (ANALYZE)
--                    over the three tables, so the space the prune freed is
--                    reusable promptly and deterministically.
-- Both slots are clear: no GitHub Actions cron runs before 06:00 UTC, the
-- Olympus run is 12:00 UTC (+up to 4 h), and the prices-live pg_cron entries
-- only fire 13:00-01:00 UTC.
--
-- To pause:
--   SELECT cron.unschedule('langgraph-checkpoint-prune');
--   SELECT cron.unschedule('langgraph-checkpoint-vacuum');
--
-- SAFETY ------------------------------------------------------------------
-- * Retention can never be zero. `pipeline-olympus.yml:32` exposes a
--   `resume_run_id` input that resumes a prior run's checkpoint thread, so old
--   threads are load-bearing; `retain_days` is validated `>= 1` and the
--   resume window is now explicitly capped at the retention window.
-- * The stale set is keyed on `max((checkpoint->>'ts')::timestamptz)` PER
--   THREAD, so an in-flight or freshly-resumed run is never eligible — not
--   even at `retain_days = 1`. Measured: 0 of 1486 rows have a NULL `ts`, and
--   a thread whose timestamps were all NULL would yield NULL from `max()`,
--   which fails the `<` predicate and is therefore RETAINED (fail-safe).
-- * Thread-scoped deletion is complete: `checkpoint_blobs` is keyed
--   `(thread_id, checkpoint_ns, channel, version)` with no `checkpoint_id`, so
--   per-checkpoint deletion would orphan blobs. Verified 2026-08-01 that zero
--   `checkpoint_writes` / `checkpoint_blobs` threads lack a `checkpoints` row,
--   so no orphan class is missed. `checkpoint_migrations` (LangGraph's own
--   schema-version table, 10 rows) is deliberately untouched.
-- * The DELETEs drive exactly the `checkpoint_writes_thread_id_idx` /
--   `checkpoint_blobs_thread_id_idx` indexes that the Supabase advisor was
--   reported to have flagged as unused — that report was wrong (both show
--   nonzero idx_scan), and after this migration they are load-bearing.
-- * `VACUUM FULL` is deliberately NOT used: it takes an ACCESS EXCLUSIVE lock,
--   and these tables carry no bloat to reclaim (886 MB live compressed vs
--   940 MB on disk; 427-497 heap bytes/row), so it would buy nothing at the
--   cost of blocking the pipeline.
-- * No VACUUM appears in this file. db-migrate.yml applies unwrapped
--   migrations with `--single-transaction`, and VACUUM cannot run inside a
--   transaction block — it would abort and roll the whole migration back.
--   VACUUM therefore lives only in the cron job, which pg_cron runs as a
--   single statement outside an explicit transaction.
-- * Not a CLAUDE.md human gate: pg_cron 1.6.4 is already installed and already
--   used in this project (see README.md, the prices-live entries); no new
--   extension, no `pg_net`, no network egress, no new external dependency.
--
-- VERIFY AFTER PROMOTION TO main ------------------------------------------
--   SELECT jobname, username, database, schedule, active
--     FROM cron.job WHERE jobname LIKE 'langgraph-checkpoint%';
--     -- expect 2 rows, username = 'postgres', database = 'postgres'
--   SELECT jobname, status, return_message, start_time
--     FROM cron.job_run_details d JOIN cron.job j USING (jobid)
--    WHERE j.jobname LIKE 'langgraph-checkpoint%'
--    ORDER BY start_time DESC LIMIT 4;
--
-- Idempotent: CREATE OR REPLACE, re-runnable REVOKE/COMMENT, and pg_cron 1.6.4
-- `cron.schedule` upserts by (username, jobname).

-- ---------------------------------------------------------------------------
-- Install-time role assertion.
--
-- The cron jobs run as the role that called cron.schedule, i.e. whatever role
-- DIGI_CHECKPOINTER_POSTGRES_URI authenticates as. If that role does not own
-- the checkpointer tables, both halves fail SILENTLY: RLS is enabled with no
-- policy, so a non-owner DELETE affects 0 rows without error, and a non-owner
-- VACUUM emits a WARNING and skips the table. A retention job that prunes
-- nothing forever is worse than no retention job, so fail loudly at apply time
-- instead. Verified 2026-08-01: all four checkpointer tables are owned by
-- `postgres`, RLS is enabled WITHOUT force, so the owner bypasses RLS.
-- ---------------------------------------------------------------------------
DO $mig$
DECLARE
  bad_owner text;
BEGIN
  SELECT string_agg(c.relname || ' (owner ' || pg_get_userbyid(c.relowner) || ')', ', ')
    INTO bad_owner
    FROM pg_class c
    JOIN pg_namespace n ON n.oid = c.relnamespace
   WHERE n.nspname = 'public'
     AND c.relname IN ('checkpoints', 'checkpoint_writes', 'checkpoint_blobs')
     AND NOT pg_has_role(current_user, c.relowner, 'USAGE');

  IF bad_owner IS NOT NULL THEN
    RAISE EXCEPTION
      'migration 061: % is not an owner of %; the retention prune would delete 0 rows '
      'and the VACUUM would be skipped, both silently. Apply as the table owner.',
      current_user, bad_owner;
  END IF;
END
$mig$;

-- ---------------------------------------------------------------------------
-- The prune. SECURITY DEFINER so the DELETEs are correct regardless of which
-- role the cron job ends up owned by (RLS-with-no-policy would otherwise turn a
-- wrong-role install into a silent 0-row prune). The injection surface is one
-- integer that is range-validated before use, `search_path` is pinned empty so
-- every name is schema-qualified, and EXECUTE is revoked from PUBLIC below so
-- this is not reachable as a PostgREST RPC by the bundled anon key.
-- ---------------------------------------------------------------------------
CREATE OR REPLACE FUNCTION public.prune_langgraph_checkpoints(retain_days integer DEFAULT 14)
RETURNS TABLE (
  threads_pruned      bigint,
  checkpoints_deleted bigint,
  writes_deleted      bigint,
  blobs_deleted       bigint
)
LANGUAGE plpgsql
SECURITY DEFINER
SET search_path = ''
AS $fn$
DECLARE
  stale_threads text[];
  n_checkpoints bigint := 0;
  n_writes      bigint := 0;
  n_blobs       bigint := 0;
BEGIN
  -- Retention must never be zero: `resume_run_id` (pipeline-olympus.yml:32)
  -- resumes a prior run's thread, so same-day threads are load-bearing.
  IF retain_days IS NULL OR retain_days < 1 THEN
    RAISE EXCEPTION 'prune_langgraph_checkpoints: retain_days must be >= 1, got %', retain_days;
  END IF;

  -- A thread is stale iff its NEWEST checkpoint predates the window. Keyed on
  -- max(), so an in-flight run can never be eligible. A thread with no parsable
  -- timestamps yields NULL, fails the predicate, and is retained.
  SELECT coalesce(array_agg(t.thread_id), '{}'::text[])
    INTO stale_threads
    FROM (
      SELECT c.thread_id
        FROM public.checkpoints c
       GROUP BY c.thread_id
      HAVING max((c.checkpoint ->> 'ts')::timestamptz)
             < clock_timestamp() - make_interval(days => retain_days)
    ) AS t;

  IF cardinality(stale_threads) = 0 THEN
    RETURN QUERY SELECT 0::bigint, 0::bigint, 0::bigint, 0::bigint;
    RETURN;
  END IF;

  -- Children before parent: `checkpoint_blobs` has no `checkpoint_id`, so it is
  -- only reachable by thread_id and must not be left behind.
  DELETE FROM public.checkpoint_writes w WHERE w.thread_id = ANY (stale_threads);
  GET DIAGNOSTICS n_writes = ROW_COUNT;

  DELETE FROM public.checkpoint_blobs b WHERE b.thread_id = ANY (stale_threads);
  GET DIAGNOSTICS n_blobs = ROW_COUNT;

  DELETE FROM public.checkpoints c WHERE c.thread_id = ANY (stale_threads);
  GET DIAGNOSTICS n_checkpoints = ROW_COUNT;

  RAISE LOG 'prune_langgraph_checkpoints(%): % threads, % checkpoints, % writes, % blobs',
    retain_days, cardinality(stale_threads), n_checkpoints, n_writes, n_blobs;

  RETURN QUERY SELECT
    cardinality(stale_threads)::bigint, n_checkpoints, n_writes, n_blobs;
END
$fn$;

-- Belt and braces alongside RLS: without this, PostgREST would expose the
-- function as `POST /rest/v1/rpc/prune_langgraph_checkpoints` to the anon key
-- that ships in the digiquant.io bundle, and SECURITY DEFINER would run it as
-- the owner. Maintenance only — the pipeline never calls it.
REVOKE ALL ON FUNCTION public.prune_langgraph_checkpoints(integer) FROM PUBLIC;
REVOKE ALL ON FUNCTION public.prune_langgraph_checkpoints(integer) FROM anon, authenticated;

COMMENT ON FUNCTION public.prune_langgraph_checkpoints(integer) IS
  'Delete every LangGraph checkpointer row for threads whose newest checkpoint is '
  'older than retain_days (default 14, user ruling D6 / #1758). Thread-scoped because '
  'checkpoint_blobs has no checkpoint_id. Caps the resume window of '
  'pipeline-olympus.yml''s resume_run_id input at the same number of days. '
  'Scheduled as pg_cron job langgraph-checkpoint-prune; not called by the pipeline.';

COMMENT ON TABLE public.checkpoints IS
  'LangGraph checkpointer (#665). Internal orchestration state, never read by the '
  'dashboard. Retention: 14 days by thread, pg_cron job langgraph-checkpoint-prune '
  '(migration 061, #1758). thread_id is "<GITHUB_RUN_ID>::atlas" / "::hermes".';

COMMENT ON TABLE public.checkpoint_writes IS
  'LangGraph checkpointer pending writes (#665). 94% of bytes are the __pregel_tasks '
  'channel: one full AtlasResearchState copy per H5/H6 fan-out target. Retention: '
  '14 days by thread, pg_cron job langgraph-checkpoint-prune (migration 061, #1758).';

COMMENT ON TABLE public.checkpoint_blobs IS
  'LangGraph checkpointer channel blobs (#665). Keyed (thread_id, checkpoint_ns, '
  'channel, version) with no checkpoint_id, so pruning MUST be thread-scoped. '
  'Retention: 14 days, pg_cron job langgraph-checkpoint-prune (migration 061, #1758).';

-- ---------------------------------------------------------------------------
-- Schedule. Guarded because a local `supabase db push` against a stack without
-- pg_cron enabled would otherwise error and roll back the entire migration;
-- prod has pg_cron 1.6.4 (verified 2026-08-01). Dynamic EXECUTE so the
-- cron.schedule reference is never even planned when the extension is absent.
-- cron.schedule upserts by (username, jobname) since pg_cron 1.4, so replaying
-- this migration re-points the existing jobs instead of duplicating them.
-- ---------------------------------------------------------------------------
DO $mig$
BEGIN
  IF NOT EXISTS (SELECT 1 FROM pg_extension WHERE extname = 'pg_cron') THEN
    RAISE NOTICE
      'migration 061: pg_cron absent, skipping schedule. The prune function is '
      'installed; schedule it manually once pg_cron is enabled.';
    RETURN;
  END IF;

  EXECUTE $q$
    SELECT cron.schedule(
      'langgraph-checkpoint-prune',
      '20 5 * * *',
      'SELECT public.prune_langgraph_checkpoints(14);'
    )
  $q$;

  -- Plain VACUUM (ANALYZE), never VACUUM FULL (ACCESS EXCLUSIVE lock, and there
  -- is no bloat to reclaim). One statement over three tables, which is what
  -- lets pg_cron run it — VACUUM is illegal inside a transaction block.
  EXECUTE $q$
    SELECT cron.schedule(
      'langgraph-checkpoint-vacuum',
      '50 5 * * *',
      'VACUUM (ANALYZE) public.checkpoints, public.checkpoint_writes, public.checkpoint_blobs;'
    )
  $q$;
END
$mig$;
