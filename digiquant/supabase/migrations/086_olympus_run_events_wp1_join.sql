-- 086_olympus_run_events_wp1_join.sql
--
-- Join glass-box ordered call telemetry (066) to the WP1 provider ledger (067) (#2763).
--
-- Authority: `olympus_provider_*` (067) remains the exact-billing / nullable-usage ledger.
-- Compatibility: `olympus_run_events` keeps ordered Pipeline call-trace rows and stamps
-- soft join keys (`call_id`, `attempt_id`, `node_run_id`) so Gate 3 can reconcile without
-- fabricating economics. Token/cost columns become nullable — missing usage stays NULL,
-- never DEFAULT 0. No hard FK to attempts: fail-soft quarantine on 067 may omit a row
-- that glass-box still needs for ordering honesty.
--
-- Public view restates with join keys only (still no tokens/cost/prompts/bodies).
-- Append-only restatement: ALTER existing columns; no historical backfill of IDs.
--
-- Unwrapped on purpose: db-migrate.yml applies the file and its ledger row in one
-- psql single-transaction call.

ALTER TABLE public.olympus_run_events
    ALTER COLUMN prompt_tokens DROP NOT NULL,
    ALTER COLUMN prompt_tokens DROP DEFAULT,
    ALTER COLUMN completion_tokens DROP NOT NULL,
    ALTER COLUMN completion_tokens DROP DEFAULT,
    ALTER COLUMN cached_tokens DROP NOT NULL,
    ALTER COLUMN cached_tokens DROP DEFAULT,
    ALTER COLUMN cost_usd DROP NOT NULL,
    ALTER COLUMN cost_usd DROP DEFAULT;

ALTER TABLE public.olympus_run_events
    DROP CONSTRAINT IF EXISTS olympus_run_events_prompt_tokens_check,
    DROP CONSTRAINT IF EXISTS olympus_run_events_completion_tokens_check,
    DROP CONSTRAINT IF EXISTS olympus_run_events_cached_tokens_check,
    DROP CONSTRAINT IF EXISTS olympus_run_events_cost_usd_check;

ALTER TABLE public.olympus_run_events
    ADD CONSTRAINT olympus_run_events_prompt_tokens_check
        CHECK (prompt_tokens IS NULL OR prompt_tokens >= 0),
    ADD CONSTRAINT olympus_run_events_completion_tokens_check
        CHECK (completion_tokens IS NULL OR completion_tokens >= 0),
    ADD CONSTRAINT olympus_run_events_cached_tokens_check
        CHECK (cached_tokens IS NULL OR cached_tokens >= 0),
    ADD CONSTRAINT olympus_run_events_cost_usd_check
        CHECK (cost_usd IS NULL OR cost_usd >= 0);

ALTER TABLE public.olympus_run_events
    ADD COLUMN IF NOT EXISTS call_id uuid,
    ADD COLUMN IF NOT EXISTS attempt_id uuid,
    ADD COLUMN IF NOT EXISTS node_run_id uuid;

CREATE INDEX IF NOT EXISTS olympus_run_events_attempt_id_idx
    ON public.olympus_run_events (attempt_id)
    WHERE attempt_id IS NOT NULL;

CREATE INDEX IF NOT EXISTS olympus_run_events_call_id_idx
    ON public.olympus_run_events (call_id)
    WHERE call_id IS NOT NULL;

COMMENT ON COLUMN public.olympus_run_events.call_id IS
  'Soft stamp to olympus_provider_calls.call_id (067). WP1 is billing authority; NULL when '
  'the glass-box row has no corresponding logical call (e.g. tool_call).';
COMMENT ON COLUMN public.olympus_run_events.attempt_id IS
  'Soft stamp to olympus_provider_attempts.attempt_id (067) for Gate 3 reconciliation.';
COMMENT ON COLUMN public.olympus_run_events.node_run_id IS
  'Soft stamp to olympus_node_runs.node_run_id (067) when the event ran inside a node scope.';
COMMENT ON COLUMN public.olympus_run_events.prompt_tokens IS
  'Nullable operator telemetry. Missing usage stays NULL — never fabricate 0. Prefer 067 '
  'attempt rows for exact billing.';
COMMENT ON COLUMN public.olympus_run_events.completion_tokens IS
  'Nullable operator telemetry. Missing usage stays NULL — never fabricate 0.';
COMMENT ON COLUMN public.olympus_run_events.cached_tokens IS
  'Nullable operator telemetry. Missing usage stays NULL — never fabricate 0.';
COMMENT ON COLUMN public.olympus_run_events.cost_usd IS
  'Nullable operator telemetry. Missing cost stays NULL — never fabricate 0. Prefer 067.';

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
    created_at,
    call_id,
    attempt_id,
    node_run_id
FROM public.olympus_run_events;

COMMENT ON VIEW public.olympus_run_event_trace IS
  'Curated Olympus Pipeline call trace. Exposes fixed operation metadata, shape summaries, '
  'and WP1 soft join keys (call_id/attempt_id/node_run_id). Excludes prompts, values, '
  'results, reasoning, tokens, and cost — economics authority is olympus_provider_attempts.';

REVOKE ALL ON public.olympus_run_event_trace FROM anon, authenticated;
GRANT SELECT ON public.olympus_run_event_trace TO anon, authenticated;
