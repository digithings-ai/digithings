-- 066_olympus_run_events.sql
--
-- Ordered, body-free call telemetry for the Olympus Pipeline inspector (#1945).
-- The base table is service-role-only because token and cost fields are operator
-- telemetry. The public view projects only fixed labels, timing, status, and
-- code-generated shape summaries. No prompt, tool argument value, tool result,
-- document body, bearer token, or model reasoning is accepted by this schema.

CREATE TABLE IF NOT EXISTS public.olympus_run_events (
    run_id            text NOT NULL CHECK (char_length(run_id) <= 255),
    attempt           integer NOT NULL,
    run_date          date NOT NULL,
    run_type          text CHECK (run_type IS NULL OR char_length(run_type) <= 100),
    sequence          integer NOT NULL CHECK (sequence > 0),
    event_kind        text NOT NULL CHECK (
        event_kind IN ('model_call', 'search_call', 'tool_call')
    ),
    phase             text CHECK (phase IS NULL OR char_length(phase) <= 120),
    operation         text CHECK (operation IS NULL OR char_length(operation) <= 200),
    document_key      text CHECK (document_key IS NULL OR char_length(document_key) <= 500),
    name              text NOT NULL CHECK (char_length(name) <= 255),
    status            text NOT NULL CHECK (status IN ('ok', 'error')),
    duration_ms       integer CHECK (duration_ms IS NULL OR duration_ms >= 0),
    retry_count       integer NOT NULL DEFAULT 0 CHECK (retry_count >= 0),
    prompt_tokens     bigint NOT NULL DEFAULT 0 CHECK (prompt_tokens >= 0),
    completion_tokens bigint NOT NULL DEFAULT 0 CHECK (completion_tokens >= 0),
    cached_tokens     bigint NOT NULL DEFAULT 0 CHECK (cached_tokens >= 0),
    cost_usd          numeric NOT NULL DEFAULT 0 CHECK (cost_usd >= 0),
    sources           integer NOT NULL DEFAULT 0 CHECK (sources >= 0),
    input_summary     text NOT NULL CHECK (char_length(input_summary) <= 500),
    output_summary    text NOT NULL CHECK (char_length(output_summary) <= 500),
    created_at        timestamptz NOT NULL DEFAULT now(),
    PRIMARY KEY (run_id, attempt, sequence)
);

CREATE INDEX IF NOT EXISTS olympus_run_events_run_date_idx
    ON public.olympus_run_events (run_date DESC, attempt, sequence);
CREATE INDEX IF NOT EXISTS olympus_run_events_phase_idx
    ON public.olympus_run_events (run_date DESC, phase);

ALTER TABLE public.olympus_run_events ENABLE ROW LEVEL SECURITY;

REVOKE ALL ON public.olympus_run_events FROM anon, authenticated;

DROP POLICY IF EXISTS olympus_run_events_anon_select ON public.olympus_run_events;
DROP POLICY IF EXISTS olympus_run_events_authenticated_select ON public.olympus_run_events;

COMMENT ON TABLE public.olympus_run_events IS
  'Service-role-only ordered Olympus call telemetry. Body-free by contract: never store '
  'prompts, tool argument values, tool results, document bodies, credentials, or reasoning.';

CREATE OR REPLACE VIEW public.olympus_run_event_trace
WITH (security_invoker = false) AS
SELECT
    run_id,
    attempt,
    run_date,
    run_type,
    sequence,
    event_kind,
    phase,
    operation,
    document_key,
    name,
    status,
    duration_ms,
    retry_count,
    sources,
    input_summary,
    output_summary,
    created_at
FROM public.olympus_run_events;

COMMENT ON VIEW public.olympus_run_event_trace IS
  'Curated Olympus Pipeline call trace. Exposes fixed operation metadata and code-generated '
  'shape summaries only; excludes prompts, values, results, reasoning, tokens, and cost.';

REVOKE ALL ON public.olympus_run_event_trace FROM anon, authenticated;
GRANT SELECT ON public.olympus_run_event_trace TO anon, authenticated;