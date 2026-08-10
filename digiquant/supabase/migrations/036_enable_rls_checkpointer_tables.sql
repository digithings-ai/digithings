-- 036_enable_rls_checkpointer_tables.sql — lock down the LangGraph Postgres
-- checkpointer tables (security follow-up; advisor lint 0013_rls_disabled_in_public).
--
-- The langgraph postgres checkpointer (#665, DIGI_CHECKPOINTER) auto-creates four
-- tables in `public` — `checkpoints`, `checkpoint_writes`, `checkpoint_blobs`,
-- `checkpoint_migrations` — with RLS DISABLED. Because every `public` table is
-- exposed through PostgREST, the bundled Olympus anon key can read pipeline run
-- state from them. The dashboard never reads these tables (a repo-wide search
-- shows no frontend reference); they are internal orchestration state.
--
-- The checkpointer writes via a DIRECT Postgres connection
-- (DIGI_CHECKPOINTER_POSTGRES_URI) as the table owner (`postgres`), which bypasses
-- RLS — so enabling RLS does not affect the pipeline. With RLS enabled and no
-- policy, the anon/authenticated PostgREST roles get deny-by-default (reads return
-- an empty result set, not an error). Same hardening direction as migration 033
-- for `atlas_run_diagnostics`. Idempotent — re-enabling RLS is a no-op.

ALTER TABLE public.checkpoints ENABLE ROW LEVEL SECURITY;
ALTER TABLE public.checkpoint_writes ENABLE ROW LEVEL SECURITY;
ALTER TABLE public.checkpoint_blobs ENABLE ROW LEVEL SECURITY;
ALTER TABLE public.checkpoint_migrations ENABLE ROW LEVEL SECURITY;
