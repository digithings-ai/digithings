-- 092_olympus_attention_context.sql
--
-- Phase 3 WP13.2 private append-only attention plan/decision/context/evaluation
-- store (#2922). Persists routing evidence and WP1 provider-attempt linkage for
-- shadow/enforced reconciliation (WP13.5/WP16). Storage only — no runtime
-- Atlas/Hermes activation (WP13.3+).
--
-- Application store: digiquant.olympus.research_retrieval.store.AttentionStore.
--
-- Privacy: RLS enabled with zero policies; PUBLIC/anon/authenticated fully
-- revoked; service_role reset then SELECT+INSERT only. Append-only triggers
-- reject UPDATE/DELETE/TRUNCATE for every role. No public base view.
--
-- Unwrapped on purpose: db-migrate.yml applies the file and its ledger row in
-- one psql single-transaction call. DDL is replay-safe through IF NOT EXISTS,
-- CREATE OR REPLACE, and DROP TRIGGER IF EXISTS before CREATE TRIGGER.

CREATE TABLE IF NOT EXISTS public.olympus_attention_plans (
    plan_id uuid PRIMARY KEY,
    run_id text NOT NULL CHECK (length(run_id) BETWEEN 1 AND 500),
    attempt_id text NOT NULL CHECK (length(attempt_id) BETWEEN 1 AND 500),
    state_version_id uuid,
    policy_content_hash text NOT NULL CHECK (length(policy_content_hash) = 64),
    rollout_mode text NOT NULL CHECK (
        rollout_mode IN ('off', 'shadow', 'enforce')
    ),
    actuated boolean NOT NULL DEFAULT false,
    exploration_slots_reserved integer NOT NULL CHECK (exploration_slots_reserved >= 0),
    total_budget jsonb NOT NULL CHECK (jsonb_typeof(total_budget) = 'object'),
    recorded_at timestamptz NOT NULL,
    schema_version integer NOT NULL CHECK (schema_version >= 1),
    payload jsonb NOT NULL CHECK (jsonb_typeof(payload) = 'object'),
    CONSTRAINT uq_olympus_attention_plans_run_attempt UNIQUE (run_id, attempt_id)
);

CREATE TABLE IF NOT EXISTS public.olympus_attention_decisions (
    decision_id uuid PRIMARY KEY,
    plan_id uuid NOT NULL,
    run_id text NOT NULL CHECK (length(run_id) BETWEEN 1 AND 500),
    attempt_id text NOT NULL CHECK (length(attempt_id) BETWEEN 1 AND 500),
    target_key text NOT NULL CHECK (length(target_key) BETWEEN 1 AND 500),
    mode text NOT NULL CHECK (
        mode IN ('carry', 'metric_patch', 'section_patch', 'challenge', 'deep_refresh')
    ),
    reason text NOT NULL CHECK (length(reason) BETWEEN 1 AND 100),
    state_version_id uuid,
    policy_content_hash text NOT NULL CHECK (length(policy_content_hash) = 64),
    budget jsonb NOT NULL CHECK (jsonb_typeof(budget) = 'object'),
    exploration_reserved boolean NOT NULL DEFAULT false,
    actuated boolean NOT NULL DEFAULT false,
    recorded_at timestamptz NOT NULL,
    schema_version integer NOT NULL CHECK (schema_version >= 1),
    payload jsonb NOT NULL CHECK (jsonb_typeof(payload) = 'object'),
    CONSTRAINT fk_olympus_attention_decisions_plan
        FOREIGN KEY (plan_id)
        REFERENCES public.olympus_attention_plans (plan_id),
    CONSTRAINT uq_olympus_attention_decisions_plan_target
        UNIQUE (plan_id, target_key)
);

CREATE TABLE IF NOT EXISTS public.olympus_attention_decision_attempts (
    decision_id uuid NOT NULL,
    provider_attempt_id uuid NOT NULL,
    recorded_at timestamptz NOT NULL DEFAULT now(),
    CONSTRAINT pk_olympus_attention_decision_attempts
        PRIMARY KEY (decision_id, provider_attempt_id),
    CONSTRAINT fk_olympus_attention_decision_attempts_decision
        FOREIGN KEY (decision_id)
        REFERENCES public.olympus_attention_decisions (decision_id),
    CONSTRAINT fk_olympus_attention_decision_attempts_provider
        FOREIGN KEY (provider_attempt_id)
        REFERENCES public.olympus_provider_attempts (attempt_id)
);

CREATE TABLE IF NOT EXISTS public.olympus_attention_context_manifests (
    manifest_id uuid PRIMARY KEY,
    plan_id uuid NOT NULL,
    decision_id uuid,
    run_id text NOT NULL CHECK (length(run_id) BETWEEN 1 AND 500),
    attempt_id text NOT NULL CHECK (length(attempt_id) BETWEEN 1 AND 500),
    role text NOT NULL CHECK (length(role) BETWEEN 1 AND 100),
    state_version_id uuid,
    content_hash text NOT NULL CHECK (length(content_hash) = 64),
    included_entity_ids jsonb NOT NULL DEFAULT '[]'::jsonb
        CHECK (jsonb_typeof(included_entity_ids) = 'array'),
    omission_reasons jsonb NOT NULL DEFAULT '[]'::jsonb
        CHECK (jsonb_typeof(omission_reasons) = 'array'),
    recorded_at timestamptz NOT NULL,
    schema_version integer NOT NULL CHECK (schema_version >= 1),
    payload jsonb NOT NULL CHECK (jsonb_typeof(payload) = 'object'),
    CONSTRAINT fk_olympus_attention_context_manifests_plan
        FOREIGN KEY (plan_id)
        REFERENCES public.olympus_attention_plans (plan_id),
    CONSTRAINT fk_olympus_attention_context_manifests_decision
        FOREIGN KEY (decision_id)
        REFERENCES public.olympus_attention_decisions (decision_id)
);

CREATE TABLE IF NOT EXISTS public.olympus_attention_policy_evaluations (
    evaluation_id uuid PRIMARY KEY,
    plan_id uuid NOT NULL,
    run_id text NOT NULL CHECK (length(run_id) BETWEEN 1 AND 500),
    attempt_id text NOT NULL CHECK (length(attempt_id) BETWEEN 1 AND 500),
    rollout_mode text NOT NULL CHECK (
        rollout_mode IN ('off', 'shadow', 'enforce')
    ),
    complete boolean NOT NULL,
    planned_total jsonb NOT NULL CHECK (jsonb_typeof(planned_total) = 'object'),
    actual_total jsonb NOT NULL CHECK (jsonb_typeof(actual_total) = 'object'),
    decision_reconciliations jsonb NOT NULL DEFAULT '[]'::jsonb
        CHECK (jsonb_typeof(decision_reconciliations) = 'array'),
    recorded_at timestamptz NOT NULL,
    schema_version integer NOT NULL CHECK (schema_version >= 1),
    payload jsonb NOT NULL CHECK (jsonb_typeof(payload) = 'object'),
    CONSTRAINT fk_olympus_attention_policy_evaluations_plan
        FOREIGN KEY (plan_id)
        REFERENCES public.olympus_attention_plans (plan_id)
);

CREATE INDEX IF NOT EXISTS idx_olympus_attention_plans_recorded
    ON public.olympus_attention_plans (recorded_at);

CREATE INDEX IF NOT EXISTS idx_olympus_attention_decisions_plan
    ON public.olympus_attention_decisions (plan_id);

CREATE INDEX IF NOT EXISTS idx_olympus_attention_decisions_recorded
    ON public.olympus_attention_decisions (recorded_at);

CREATE INDEX IF NOT EXISTS idx_olympus_attention_context_manifests_plan
    ON public.olympus_attention_context_manifests (plan_id);

CREATE INDEX IF NOT EXISTS idx_olympus_attention_policy_evaluations_plan
    ON public.olympus_attention_policy_evaluations (plan_id);

ALTER TABLE public.olympus_attention_plans ENABLE ROW LEVEL SECURITY;
ALTER TABLE public.olympus_attention_decisions ENABLE ROW LEVEL SECURITY;
ALTER TABLE public.olympus_attention_decision_attempts ENABLE ROW LEVEL SECURITY;
ALTER TABLE public.olympus_attention_context_manifests ENABLE ROW LEVEL SECURITY;
ALTER TABLE public.olympus_attention_policy_evaluations ENABLE ROW LEVEL SECURITY;

REVOKE ALL ON public.olympus_attention_plans FROM PUBLIC, anon, authenticated;
REVOKE ALL ON public.olympus_attention_decisions FROM PUBLIC, anon, authenticated;
REVOKE ALL ON public.olympus_attention_decision_attempts FROM PUBLIC, anon, authenticated;
REVOKE ALL ON public.olympus_attention_context_manifests FROM PUBLIC, anon, authenticated;
REVOKE ALL ON public.olympus_attention_policy_evaluations FROM PUBLIC, anon, authenticated;

REVOKE ALL ON public.olympus_attention_plans FROM service_role;
REVOKE ALL ON public.olympus_attention_decisions FROM service_role;
REVOKE ALL ON public.olympus_attention_decision_attempts FROM service_role;
REVOKE ALL ON public.olympus_attention_context_manifests FROM service_role;
REVOKE ALL ON public.olympus_attention_policy_evaluations FROM service_role;

GRANT SELECT, INSERT ON public.olympus_attention_plans TO service_role;
GRANT SELECT, INSERT ON public.olympus_attention_decisions TO service_role;
GRANT SELECT, INSERT ON public.olympus_attention_decision_attempts TO service_role;
GRANT SELECT, INSERT ON public.olympus_attention_context_manifests TO service_role;
GRANT SELECT, INSERT ON public.olympus_attention_policy_evaluations TO service_role;

CREATE OR REPLACE FUNCTION public.reject_olympus_attention_context_mutation()
RETURNS trigger
LANGUAGE plpgsql
SET search_path = ''
AS $$
BEGIN
    RAISE EXCEPTION 'attention context store is append-only (#2922)'
        USING ERRCODE = '55000';
END
$$;

DROP TRIGGER IF EXISTS reject_olympus_attention_plans_mutation
    ON public.olympus_attention_plans;
CREATE TRIGGER reject_olympus_attention_plans_mutation
    BEFORE UPDATE OR DELETE ON public.olympus_attention_plans
    FOR EACH ROW EXECUTE FUNCTION public.reject_olympus_attention_context_mutation();
DROP TRIGGER IF EXISTS reject_olympus_attention_plans_truncate
    ON public.olympus_attention_plans;
CREATE TRIGGER reject_olympus_attention_plans_truncate
    BEFORE TRUNCATE ON public.olympus_attention_plans
    FOR EACH STATEMENT EXECUTE FUNCTION public.reject_olympus_attention_context_mutation();

DROP TRIGGER IF EXISTS reject_olympus_attention_decisions_mutation
    ON public.olympus_attention_decisions;
CREATE TRIGGER reject_olympus_attention_decisions_mutation
    BEFORE UPDATE OR DELETE ON public.olympus_attention_decisions
    FOR EACH ROW EXECUTE FUNCTION public.reject_olympus_attention_context_mutation();
DROP TRIGGER IF EXISTS reject_olympus_attention_decisions_truncate
    ON public.olympus_attention_decisions;
CREATE TRIGGER reject_olympus_attention_decisions_truncate
    BEFORE TRUNCATE ON public.olympus_attention_decisions
    FOR EACH STATEMENT EXECUTE FUNCTION public.reject_olympus_attention_context_mutation();

DROP TRIGGER IF EXISTS reject_olympus_attention_decision_attempts_mutation
    ON public.olympus_attention_decision_attempts;
CREATE TRIGGER reject_olympus_attention_decision_attempts_mutation
    BEFORE UPDATE OR DELETE ON public.olympus_attention_decision_attempts
    FOR EACH ROW EXECUTE FUNCTION public.reject_olympus_attention_context_mutation();
DROP TRIGGER IF EXISTS reject_olympus_attention_decision_attempts_truncate
    ON public.olympus_attention_decision_attempts;
CREATE TRIGGER reject_olympus_attention_decision_attempts_truncate
    BEFORE TRUNCATE ON public.olympus_attention_decision_attempts
    FOR EACH STATEMENT EXECUTE FUNCTION public.reject_olympus_attention_context_mutation();

DROP TRIGGER IF EXISTS reject_olympus_attention_context_manifests_mutation
    ON public.olympus_attention_context_manifests;
CREATE TRIGGER reject_olympus_attention_context_manifests_mutation
    BEFORE UPDATE OR DELETE ON public.olympus_attention_context_manifests
    FOR EACH ROW EXECUTE FUNCTION public.reject_olympus_attention_context_mutation();
DROP TRIGGER IF EXISTS reject_olympus_attention_context_manifests_truncate
    ON public.olympus_attention_context_manifests;
CREATE TRIGGER reject_olympus_attention_context_manifests_truncate
    BEFORE TRUNCATE ON public.olympus_attention_context_manifests
    FOR EACH STATEMENT EXECUTE FUNCTION public.reject_olympus_attention_context_mutation();

DROP TRIGGER IF EXISTS reject_olympus_attention_policy_evaluations_mutation
    ON public.olympus_attention_policy_evaluations;
CREATE TRIGGER reject_olympus_attention_policy_evaluations_mutation
    BEFORE UPDATE OR DELETE ON public.olympus_attention_policy_evaluations
    FOR EACH ROW EXECUTE FUNCTION public.reject_olympus_attention_context_mutation();
DROP TRIGGER IF EXISTS reject_olympus_attention_policy_evaluations_truncate
    ON public.olympus_attention_policy_evaluations;
CREATE TRIGGER reject_olympus_attention_policy_evaluations_truncate
    BEFORE TRUNCATE ON public.olympus_attention_policy_evaluations
    FOR EACH STATEMENT EXECUTE FUNCTION public.reject_olympus_attention_context_mutation();
