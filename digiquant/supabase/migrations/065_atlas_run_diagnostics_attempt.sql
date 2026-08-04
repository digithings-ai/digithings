-- 065_atlas_run_diagnostics_attempt.sql
--
-- Run with:  supabase db push   (or paste into the Supabase SQL editor / apply via MCP)
--
-- Key atlas_run_diagnostics per RETRY ATTEMPT, not per workflow run (#1762).
--
-- pipeline-olympus.yml retries the chain up to 3 times inside ONE job (MAX_OUTER_ATTEMPTS=3,
-- OUTER_BACKOFF=(0 300 900)), and every attempt writes its telemetry keyed on the bare
-- GITHUB_RUN_ID with `upsert(..., on_conflict="run_id")`. So the LAST attempt — usually the
-- cheap checkpoint-resumed one — overwrote the expensive attempt's tokens and cost. The
-- surviving row is not merely incomplete, it is internally impossible: run 29688378908
-- (2026-07-19) records 27 fresh baseline research segments produced by 1 LLM call in 55.6s
-- for $0.0252, over a step that actually ran 23m41s.
--
-- `created_at` is the tell, and the reason this is measurable at all: diagnostics._row() omits
-- it, so ON CONFLICT DO UPDATE leaves the FIRST insert's value in place while replacing every
-- other column. 28 of 54 rows (52%) therefore satisfy `created_at < started_at` — a row whose
-- own creation predates the run it claims to describe. Run 29688378908's gap is 304.01s, which
-- is OUTER_BACKOFF[1]=300 plus process start.
--
-- WHY NOT a composite run_id value ("<GITHUB_RUN_ID>#2"): run_id is the resume handle.
-- chain.py's `_thread_base = resume_run_id or run_id` builds the LangGraph checkpoint thread
-- from it, and `--resume-run-id` takes a bare GITHUB_RUN_ID. Overloading the column would
-- make the telemetry key and the resume key disagree.
--
-- WHY NOT fold the prior attempt into `breakdown`: SUM(est_cost_usd) would still undercount,
-- and the whole complaint is that every cost figure from this table is a floor rather than
-- spend. Cost accounting needs rows.
--
-- Safe to drop the primary key: pg_constraint confirms `atlas_run_diagnostics_pkey
-- PRIMARY KEY (run_id)` is the only constraint on the table and NOTHING references
-- atlas_run_diagnostics — zero foreign keys point at it (verified against the live core
-- project, 2026-08-04). The 041 `atlas_run_health` view selects columns, not the key, so it is
-- unaffected by the PK change.
--
-- ATTEMPT 0 IS THE LEGACY SENTINEL, AND IT IS DELIBERATELY NOT 1. Backfilling `attempt = 1`
-- would assert that each of the 54 existing rows is a first attempt, when 28 of them are
-- provably a LATER attempt that destroyed its predecessor. That is the same fabrication this
-- migration exists to stop, so every pre-existing row gets 0 — "written before per-attempt
-- keying; may be a collapsed multi-attempt row". A CASE on `created_at < started_at` was
-- rejected too: the detector has false negatives (an attempt 1 that died before its own
-- diagnostics write leaves no prior insert, so its row reads clean), and guessing 1 on those
-- is the same fabrication in a smaller dose. Attempts are 1-based, so 0 can never collide with
-- a real value. Nothing consumes the legacy value — frontend/olympus/lib/run-episodes.ts
-- counts rows and orders by created_at.
--
-- Unwrapped on purpose: db-migrate.yml runs an unwrapped file and its ledger INSERT in ONE
-- psql --single-transaction call, so the version is recorded iff the DDL commits. Do NOT add an
-- explicit transaction block — that opts into the two-call path where a crash between them
-- leaves prod migrated with a silent ledger.
--
-- And do not write the transaction-start keyword followed by a semicolon ANYWHERE in this file,
-- including in a comment. db-migrate.yml's detector is
-- `grep -qiE '(^|[[:space:]])begin[[:space:]]*;'` over the raw file — it does not strip
-- comments, so prose mentioning that keyword silently reroutes the migration onto the
-- non-atomic path. The `DO $$ ... BEGIN ... END $$;` blocks below are safe: their block keyword
-- is followed by a statement, never by a semicolon.
--
-- Idempotent: every step is IF NOT EXISTS / conditional on catalog state, so a replay after a
-- partial failure is a no-op rather than an error.

-- 1. The attempt column. NOT NULL with the legacy sentinel as its default, so existing rows
--    are stamped 0 in the same statement and no separate UPDATE is needed. New rows always
--    receive an explicit value from diagnostics._row(), so the default never applies to them.
ALTER TABLE public.atlas_run_diagnostics
    ADD COLUMN IF NOT EXISTS attempt integer NOT NULL DEFAULT 0;

-- 2. Swap the primary key run_id → (run_id, attempt). Guarded on the catalog so a replay
--    neither errors on the missing old key nor on the already-present new one.
DO $$
BEGIN
    IF EXISTS (
        SELECT 1 FROM pg_constraint
        WHERE conrelid = 'public.atlas_run_diagnostics'::regclass
          AND conname = 'atlas_run_diagnostics_pkey'
          AND pg_get_constraintdef(oid) = 'PRIMARY KEY (run_id)'
    ) THEN
        ALTER TABLE public.atlas_run_diagnostics DROP CONSTRAINT atlas_run_diagnostics_pkey;
    END IF;

    IF NOT EXISTS (
        SELECT 1 FROM pg_constraint
        WHERE conrelid = 'public.atlas_run_diagnostics'::regclass
          AND contype = 'p'
    ) THEN
        ALTER TABLE public.atlas_run_diagnostics
            ADD CONSTRAINT atlas_run_diagnostics_pkey PRIMARY KEY (run_id, attempt);
    END IF;
END $$;

-- 3. Lookups by run_id alone are no longer served by the PK's leading column for equality on
--    the second column, but they still are for run_id — the composite PK's index has run_id
--    first, so `WHERE run_id = ?` remains index-served. No extra index needed.

COMMENT ON COLUMN public.atlas_run_diagnostics.attempt IS
  'Outer-retry attempt number within one workflow run, 1-based, threaded from '
  'pipeline-olympus.yml via OLYMPUS_ATTEMPT (#1762). Part of the primary key with run_id, so '
  'each attempt keeps its own tokens/cost/status instead of the last one overwriting the rest. '
  '0 means the row predates per-attempt keying and MAY be a collapsed multi-attempt row whose '
  'earlier attempts telemetry is unrecoverable — 28 of the 54 rows extant at migration time '
  'satisfied created_at < started_at, which proves a prior insert was overwritten. Never '
  'treat 0 as "first attempt".';

-- 4. Expose `attempt` on the anon-readable health view (041). It is a run-shape fact, not
--    spend, so it does not widen the 033/041 exposure boundary — est_cost_usd, token counts,
--    error_summary and breakdown all stay omitted.
--
--    APPENDED AT THE END OF THE SELECT LIST, not next to run_id: CREATE OR REPLACE VIEW can
--    only add columns after the existing ones. Reordering raises
--    "cannot change name of view column" and the whole migration fails.
CREATE OR REPLACE VIEW public.atlas_run_health
WITH (security_invoker = false) AS
SELECT
    run_id,
    run_date,
    run_type,
    model,
    status,
    started_at,
    finished_at,
    duration_s,
    segments_total,
    segments_ok,
    segments_carried,
    segments_failed,
    created_at,
    attempt
FROM public.atlas_run_diagnostics;

COMMENT ON VIEW public.atlas_run_health IS
  'Curated, anon-readable projection of atlas_run_diagnostics for the Olympus observability '
  'dashboard: run status, segment success/carry/fail counts, model, timing, and the retry '
  'attempt number ONLY. Deliberately excludes est_cost_usd, token counts, error_summary, and '
  'the breakdown JSONB (operator-internal spend telemetry revoked from anon in migration 033). '
  'Security-definer by design so it bypasses the base-table RLS while the column projection '
  'enforces the allowlist. One row per retry ATTEMPT since 065 (#1762) — a date that took three '
  'attempts has three rows, which is what run-episodes.ts groupRunEpisodes was built to read.';

GRANT SELECT ON public.atlas_run_health TO anon, authenticated;
