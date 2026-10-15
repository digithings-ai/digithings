-- 032_atlas_run_diagnostics.sql
--
-- Run with:  supabase db push   (or paste into the Supabase SQL editor / apply via MCP)
--
-- Per-run live-diagnosis table (#663): one row per Atlas/Hermes pipeline run capturing
-- LLM + Live-Search usage (tokens, sources), an ESTIMATED cost, segment success/carry
-- counts, status, timing, and a per-phase JSONB breakdown. Written fail-soft by the chain
-- (digiquant.olympus.atlas.diagnostics.write_row) at run end; the service role bypasses RLS.
-- Anon read mirrors the other public reference tables so an Olympus dashboard can query it.
-- Idempotent.

CREATE TABLE IF NOT EXISTS public.atlas_run_diagnostics (
    run_id            text PRIMARY KEY,
    run_type          text,
    run_date          date,
    model             text,
    status            text,
    started_at        timestamptz,
    finished_at       timestamptz,
    duration_s        numeric,
    llm_calls         integer,
    prompt_tokens     bigint,
    completion_tokens bigint,
    total_tokens      bigint,
    search_calls      integer,
    sources_used      integer,
    grounding_ok      integer,
    grounding_failed  integer,
    est_cost_usd      numeric,
    segments_total    integer,
    segments_ok       integer,
    segments_carried  integer,
    segments_failed   integer,
    error_summary     text,
    breakdown         jsonb,
    created_at        timestamptz NOT NULL DEFAULT now()
);

CREATE INDEX IF NOT EXISTS atlas_run_diagnostics_run_date_idx
    ON public.atlas_run_diagnostics (run_date DESC);
CREATE INDEX IF NOT EXISTS atlas_run_diagnostics_created_at_idx
    ON public.atlas_run_diagnostics (created_at DESC);

ALTER TABLE public.atlas_run_diagnostics ENABLE ROW LEVEL SECURITY;

DROP POLICY IF EXISTS atlas_run_diagnostics_anon_select ON public.atlas_run_diagnostics;
CREATE POLICY atlas_run_diagnostics_anon_select
    ON public.atlas_run_diagnostics
    FOR SELECT TO anon
    USING (true);
