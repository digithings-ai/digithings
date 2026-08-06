-- 067_olympus_provider_telemetry.sql
--
-- Private append-only vocabulary for node executions, logical provider calls, and physical
-- provider attempts (#1951). This migration stores identity, lifecycle, usage, cost, and generic
-- artifact references only. Prompts, responses, search text, secrets, and raw exceptions have no
-- columns and therefore cannot enter this ledger accidentally.
--
-- Event times come from the producer (`started_at`, `finished_at`); `recorded_at` is the database
-- write clock. Missing provider usage and cost remain NULL rather than being fabricated as zero.
--
-- RLS is enabled with no policies, and all privileges are revoked from client roles. service_role
-- receives SELECT and INSERT only. A trigger rejects UPDATE and DELETE for every role, including
-- owner-class maintenance sessions, so corrections must append superseding records in later work.
--
-- Unwrapped on purpose: db-migrate.yml applies the file and its ledger row in one psql
-- single-transaction call. All DDL is replay-safe through IF NOT EXISTS and trigger replacement.

CREATE TABLE IF NOT EXISTS public.olympus_node_runs (
    node_run_id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
    run_id text NOT NULL CHECK (length(run_id) > 0),
    node_name text NOT NULL CHECK (length(node_name) > 0),
    outcome text NOT NULL CHECK (outcome IN ('started', 'succeeded', 'failed', 'cancelled')),
    artifacts jsonb NOT NULL DEFAULT '[]'::jsonb CHECK (jsonb_typeof(artifacts) = 'array'),
    started_at timestamptz NOT NULL,
    finished_at timestamptz,
    recorded_at timestamptz NOT NULL DEFAULT now(),
    CONSTRAINT chk_olympus_node_runs_time_order
        CHECK (finished_at IS NULL OR finished_at >= started_at),
    CONSTRAINT chk_olympus_node_runs_lifecycle
        CHECK (
            (outcome = 'started' AND finished_at IS NULL)
            OR (outcome <> 'started' AND finished_at IS NOT NULL)
        )
);

CREATE TABLE IF NOT EXISTS public.olympus_provider_calls (
    call_id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
    node_run_id uuid NOT NULL,
    parent_call_id uuid,
    purpose text NOT NULL CHECK (
        purpose IN (
            'chat_completion',
            'structured_completion',
            'tool_loop',
            'web_search',
            'x_search',
            'embedding'
        )
    ),
    requested_model text NOT NULL CHECK (length(requested_model) > 0),
    cache_status text NOT NULL CHECK (
        cache_status IN ('bypassed', 'hit', 'miss', 'unavailable')
    ),
    outcome text NOT NULL CHECK (outcome IN ('started', 'succeeded', 'failed', 'cancelled')),
    attempt_count integer NOT NULL CHECK (attempt_count >= 0),
    artifacts jsonb NOT NULL DEFAULT '[]'::jsonb CHECK (jsonb_typeof(artifacts) = 'array'),
    started_at timestamptz NOT NULL,
    finished_at timestamptz,
    recorded_at timestamptz NOT NULL DEFAULT now(),
    CONSTRAINT fk_olympus_provider_calls_node_run
        FOREIGN KEY (node_run_id)
        REFERENCES public.olympus_node_runs (node_run_id),
    CONSTRAINT fk_olympus_provider_calls_parent
        FOREIGN KEY (parent_call_id)
        REFERENCES public.olympus_provider_calls (call_id),
    CONSTRAINT chk_olympus_provider_calls_time_order
        CHECK (finished_at IS NULL OR finished_at >= started_at),
    CONSTRAINT chk_olympus_provider_calls_lifecycle
        CHECK (
            (outcome = 'started' AND finished_at IS NULL)
            OR (outcome <> 'started' AND finished_at IS NOT NULL)
        ),
    CONSTRAINT chk_olympus_provider_calls_attempts
        CHECK (
            (cache_status = 'hit' AND attempt_count = 0)
            OR (cache_status <> 'hit' AND (outcome <> 'succeeded' OR attempt_count > 0))
        )
);

CREATE TABLE IF NOT EXISTS public.olympus_provider_attempts (
    attempt_id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
    call_id uuid NOT NULL,
    attempt_number integer NOT NULL CHECK (attempt_number > 0),
    provider text NOT NULL CHECK (length(provider) > 0),
    requested_model text NOT NULL CHECK (length(requested_model) > 0),
    served_model text CHECK (served_model IS NULL OR length(served_model) > 0),
    outcome text NOT NULL CHECK (outcome IN ('started', 'succeeded', 'failed', 'cancelled')),
    retry_reason text NOT NULL CHECK (
        retry_reason IN (
            'not_applicable',
            'rate_limit',
            'timeout',
            'connection_error',
            'empty_response',
            'server_error',
            'unknown'
        )
    ),
    prompt_tokens bigint CHECK (prompt_tokens IS NULL OR prompt_tokens >= 0),
    completion_tokens bigint CHECK (completion_tokens IS NULL OR completion_tokens >= 0),
    cost_usd numeric CHECK (cost_usd IS NULL OR cost_usd >= 0),
    error_type text CHECK (error_type IS NULL OR length(error_type) > 0),
    started_at timestamptz NOT NULL,
    finished_at timestamptz,
    recorded_at timestamptz NOT NULL DEFAULT now(),
    CONSTRAINT fk_olympus_provider_attempts_call
        FOREIGN KEY (call_id)
        REFERENCES public.olympus_provider_calls (call_id),
    CONSTRAINT uq_olympus_provider_attempts_sequence UNIQUE (call_id, attempt_number),
    CONSTRAINT chk_olympus_provider_attempts_time_order
        CHECK (finished_at IS NULL OR finished_at >= started_at),
    CONSTRAINT chk_olympus_provider_attempts_lifecycle
        CHECK (
            (outcome = 'started' AND finished_at IS NULL)
            OR (outcome <> 'started' AND finished_at IS NOT NULL)
        ),
    CONSTRAINT chk_olympus_provider_attempts_retry
        CHECK (
            (attempt_number = 1 AND retry_reason = 'not_applicable')
            OR (attempt_number > 1 AND retry_reason <> 'not_applicable')
        )
);

CREATE INDEX IF NOT EXISTS idx_olympus_node_runs_run_id
    ON public.olympus_node_runs (run_id, started_at);

CREATE INDEX IF NOT EXISTS idx_olympus_provider_calls_node_run_id
    ON public.olympus_provider_calls (node_run_id, started_at);

ALTER TABLE public.olympus_node_runs ENABLE ROW LEVEL SECURITY;
ALTER TABLE public.olympus_provider_calls ENABLE ROW LEVEL SECURITY;
ALTER TABLE public.olympus_provider_attempts ENABLE ROW LEVEL SECURITY;

REVOKE ALL ON public.olympus_node_runs FROM PUBLIC, anon, authenticated;
REVOKE ALL ON public.olympus_provider_calls FROM PUBLIC, anon, authenticated;
REVOKE ALL ON public.olympus_provider_attempts FROM PUBLIC, anon, authenticated;

GRANT SELECT, INSERT ON public.olympus_node_runs TO service_role;
GRANT SELECT, INSERT ON public.olympus_provider_calls TO service_role;
GRANT SELECT, INSERT ON public.olympus_provider_attempts TO service_role;

CREATE OR REPLACE FUNCTION public.reject_olympus_provider_telemetry_mutation()
RETURNS trigger
LANGUAGE plpgsql
SET search_path = ''
AS $$
BEGIN
    RAISE EXCEPTION 'provider telemetry is append-only'
        USING ERRCODE = '55000';
END
$$;

DROP TRIGGER IF EXISTS reject_olympus_node_runs_mutation ON public.olympus_node_runs;
CREATE TRIGGER reject_olympus_node_runs_mutation
    BEFORE UPDATE OR DELETE ON public.olympus_node_runs
    FOR EACH ROW EXECUTE FUNCTION public.reject_olympus_provider_telemetry_mutation();

DROP TRIGGER IF EXISTS reject_olympus_provider_calls_mutation
    ON public.olympus_provider_calls;
CREATE TRIGGER reject_olympus_provider_calls_mutation
    BEFORE UPDATE OR DELETE ON public.olympus_provider_calls
    FOR EACH ROW EXECUTE FUNCTION public.reject_olympus_provider_telemetry_mutation();

DROP TRIGGER IF EXISTS reject_olympus_provider_attempts_mutation
    ON public.olympus_provider_attempts;
CREATE TRIGGER reject_olympus_provider_attempts_mutation
    BEFORE UPDATE OR DELETE ON public.olympus_provider_attempts
    FOR EACH ROW EXECUTE FUNCTION public.reject_olympus_provider_telemetry_mutation();

REVOKE ALL ON FUNCTION public.reject_olympus_provider_telemetry_mutation()
    FROM PUBLIC, anon, authenticated;

COMMENT ON TABLE public.olympus_node_runs IS
    'Private append-only node execution ledger (#1951). Event times come from producers; '
    'recorded_at is the database write clock. No provider payloads are stored.';

COMMENT ON TABLE public.olympus_provider_calls IS
    'Private append-only logical provider call ledger (#1951). A proven cache hit has zero '
    'physical attempts; all non-cache successful calls have at least one.';

COMMENT ON TABLE public.olympus_provider_attempts IS
    'Private append-only physical provider attempt ledger (#1951). Missing token usage and '
    'cost remain NULL, never zero.';

COMMENT ON FUNCTION public.reject_olympus_provider_telemetry_mutation() IS
    'Rejects UPDATE and DELETE on the provider telemetry ledger; corrections append new evidence.';