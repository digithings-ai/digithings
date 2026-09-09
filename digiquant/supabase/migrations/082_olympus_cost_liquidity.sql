-- 082_olympus_cost_liquidity.sql
--
-- Private append-only cost/liquidity evidence registry (#2709 / WP7.3).
--
-- Stores immutable LiquiditySnapshot and ActionCostEstimate rows from H9 after
-- authoritative order_intent IDs exist, plus ActionCostOutcome rows resolved in
-- preflight when fills arrive. Registry failure is fail-soft and cannot rebook.
-- Phase 1 observational only — estimates do not feed turnover or sizing.
--
-- No historical INSERT ... SELECT. No public base view.
--
-- Privacy: RLS enabled with zero policies; PUBLIC/anon/authenticated fully revoked;
-- service_role reset then SELECT+INSERT only. Append-only triggers reject
-- UPDATE/DELETE/TRUNCATE for every role.

CREATE TABLE IF NOT EXISTS public.olympus_liquidity_snapshots (
    snapshot_id uuid PRIMARY KEY,
    method_version text NOT NULL CHECK (length(method_version) BETWEEN 1 AND 200),
    symbol text NOT NULL CHECK (length(symbol) BETWEEN 1 AND 20),
    as_of_session date NOT NULL,
    order_intent_id uuid NOT NULL,
    status text NOT NULL CHECK (
        status IN ('available', 'degraded', 'unpriceable', 'unavailable')
    ),
    unavailable_reason text CHECK (
        unavailable_reason IS NULL OR length(unavailable_reason) BETWEEN 1 AND 500
    ),
    content_hash text NOT NULL CHECK (length(content_hash) = 64),
    resolved_at timestamptz NOT NULL,
    snapshot_body jsonb NOT NULL CHECK (jsonb_typeof(snapshot_body) = 'object'),
    recorded_at timestamptz NOT NULL DEFAULT now()
);

CREATE TABLE IF NOT EXISTS public.olympus_action_cost_estimates (
    estimate_id uuid PRIMARY KEY,
    order_intent_id uuid NOT NULL,
    portfolio_commit_id uuid NOT NULL,
    policy_id uuid NOT NULL,
    liquidity_snapshot_id uuid NOT NULL,
    symbol text NOT NULL CHECK (length(symbol) BETWEEN 1 AND 20),
    status text NOT NULL CHECK (
        status IN ('available', 'degraded', 'unpriceable', 'unavailable')
    ),
    unavailable_reason text CHECK (
        unavailable_reason IS NULL OR length(unavailable_reason) BETWEEN 1 AND 500
    ),
    content_hash text NOT NULL CHECK (length(content_hash) = 64),
    effective_at timestamptz NOT NULL,
    estimated_at timestamptz NOT NULL,
    estimate_body jsonb NOT NULL CHECK (jsonb_typeof(estimate_body) = 'object'),
    recorded_at timestamptz NOT NULL DEFAULT now(),
    CONSTRAINT fk_olympus_action_cost_estimates_snapshot
        FOREIGN KEY (liquidity_snapshot_id)
        REFERENCES public.olympus_liquidity_snapshots (snapshot_id)
);

CREATE TABLE IF NOT EXISTS public.olympus_action_cost_outcomes (
    outcome_id uuid PRIMARY KEY,
    estimate_id uuid NOT NULL,
    execution_id uuid NOT NULL,
    order_intent_id uuid,
    status text NOT NULL CHECK (status IN ('compared', 'pending', 'unavailable')),
    unavailable_reason text CHECK (
        unavailable_reason IS NULL OR length(unavailable_reason) BETWEEN 1 AND 500
    ),
    content_hash text NOT NULL CHECK (length(content_hash) = 64),
    compared_at timestamptz NOT NULL,
    outcome_body jsonb NOT NULL CHECK (jsonb_typeof(outcome_body) = 'object'),
    recorded_at timestamptz NOT NULL DEFAULT now(),
    CONSTRAINT fk_olympus_action_cost_outcomes_estimate
        FOREIGN KEY (estimate_id)
        REFERENCES public.olympus_action_cost_estimates (estimate_id),
    CONSTRAINT uq_olympus_action_cost_outcomes_estimate_execution
        UNIQUE (estimate_id, execution_id)
);

CREATE INDEX IF NOT EXISTS idx_olympus_liquidity_snapshots_order
    ON public.olympus_liquidity_snapshots (order_intent_id);

CREATE INDEX IF NOT EXISTS idx_olympus_action_cost_estimates_order
    ON public.olympus_action_cost_estimates (order_intent_id);

CREATE INDEX IF NOT EXISTS idx_olympus_action_cost_estimates_effective
    ON public.olympus_action_cost_estimates (effective_at);

CREATE INDEX IF NOT EXISTS idx_olympus_action_cost_outcomes_estimate
    ON public.olympus_action_cost_outcomes (estimate_id);

ALTER TABLE public.olympus_liquidity_snapshots ENABLE ROW LEVEL SECURITY;
ALTER TABLE public.olympus_action_cost_estimates ENABLE ROW LEVEL SECURITY;
ALTER TABLE public.olympus_action_cost_outcomes ENABLE ROW LEVEL SECURITY;

REVOKE ALL ON public.olympus_liquidity_snapshots FROM PUBLIC, anon, authenticated;
REVOKE ALL ON public.olympus_action_cost_estimates FROM PUBLIC, anon, authenticated;
REVOKE ALL ON public.olympus_action_cost_outcomes FROM PUBLIC, anon, authenticated;

REVOKE ALL ON public.olympus_liquidity_snapshots FROM service_role;
REVOKE ALL ON public.olympus_action_cost_estimates FROM service_role;
REVOKE ALL ON public.olympus_action_cost_outcomes FROM service_role;

GRANT SELECT, INSERT ON public.olympus_liquidity_snapshots TO service_role;
GRANT SELECT, INSERT ON public.olympus_action_cost_estimates TO service_role;
GRANT SELECT, INSERT ON public.olympus_action_cost_outcomes TO service_role;

CREATE OR REPLACE FUNCTION public.reject_olympus_cost_liquidity_mutation()
RETURNS trigger
LANGUAGE plpgsql
SET search_path = ''
AS $$
BEGIN
    RAISE EXCEPTION 'cost liquidity registry is append-only (#2709)'
        USING ERRCODE = '55000';
END
$$;

DROP TRIGGER IF EXISTS reject_olympus_liquidity_snapshots_mutation
    ON public.olympus_liquidity_snapshots;
CREATE TRIGGER reject_olympus_liquidity_snapshots_mutation
    BEFORE UPDATE OR DELETE ON public.olympus_liquidity_snapshots
    FOR EACH ROW EXECUTE FUNCTION public.reject_olympus_cost_liquidity_mutation();
DROP TRIGGER IF EXISTS reject_olympus_liquidity_snapshots_truncate
    ON public.olympus_liquidity_snapshots;
CREATE TRIGGER reject_olympus_liquidity_snapshots_truncate
    BEFORE TRUNCATE ON public.olympus_liquidity_snapshots
    FOR EACH STATEMENT EXECUTE FUNCTION public.reject_olympus_cost_liquidity_mutation();

DROP TRIGGER IF EXISTS reject_olympus_action_cost_estimates_mutation
    ON public.olympus_action_cost_estimates;
CREATE TRIGGER reject_olympus_action_cost_estimates_mutation
    BEFORE UPDATE OR DELETE ON public.olympus_action_cost_estimates
    FOR EACH ROW EXECUTE FUNCTION public.reject_olympus_cost_liquidity_mutation();
DROP TRIGGER IF EXISTS reject_olympus_action_cost_estimates_truncate
    ON public.olympus_action_cost_estimates;
CREATE TRIGGER reject_olympus_action_cost_estimates_truncate
    BEFORE TRUNCATE ON public.olympus_action_cost_estimates
    FOR EACH STATEMENT EXECUTE FUNCTION public.reject_olympus_cost_liquidity_mutation();

DROP TRIGGER IF EXISTS reject_olympus_action_cost_outcomes_mutation
    ON public.olympus_action_cost_outcomes;
CREATE TRIGGER reject_olympus_action_cost_outcomes_mutation
    BEFORE UPDATE OR DELETE ON public.olympus_action_cost_outcomes
    FOR EACH ROW EXECUTE FUNCTION public.reject_olympus_cost_liquidity_mutation();
DROP TRIGGER IF EXISTS reject_olympus_action_cost_outcomes_truncate
    ON public.olympus_action_cost_outcomes;
CREATE TRIGGER reject_olympus_action_cost_outcomes_truncate
    BEFORE TRUNCATE ON public.olympus_action_cost_outcomes
    FOR EACH STATEMENT EXECUTE FUNCTION public.reject_olympus_cost_liquidity_mutation();

REVOKE ALL ON FUNCTION public.reject_olympus_cost_liquidity_mutation()
    FROM PUBLIC, anon, authenticated;

COMMENT ON TABLE public.olympus_liquidity_snapshots IS
    'Append-only prospective liquidity snapshots for action cost audit (#2709 / WP7.3).';
COMMENT ON TABLE public.olympus_action_cost_estimates IS
    'Append-only prospective action cost estimates bound to order_intent_id (#2709).';
COMMENT ON TABLE public.olympus_action_cost_outcomes IS
    'Append-only expected-vs-realized cost comparisons (#2709).';
COMMENT ON FUNCTION public.reject_olympus_cost_liquidity_mutation() IS
    'Append-only guard for olympus cost/liquidity tables (#2709).';
