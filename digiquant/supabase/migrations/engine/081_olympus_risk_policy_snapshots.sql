-- 081_olympus_risk_policy_snapshots.sql
--
-- Private append-only H8 risk policy / covariance snapshot registry (#2698 / WP6.3).
--
-- Stores immutable resolved RiskPolicy and CovarianceSnapshot rows plus one run
-- ref per source_run_id. Written prospectively through H9 after portfolio booking
-- — registry failure is fail-soft and cannot rebook. Phase 1 audit only; H8 still
-- calls incumbent ``size_portfolio`` directly.
--
-- No historical INSERT ... SELECT. No prompt/reasoning bodies. No public base view.
--
-- Privacy: RLS enabled with zero policies; PUBLIC/anon/authenticated fully revoked;
-- service_role reset then SELECT+INSERT only. Append-only triggers reject
-- UPDATE/DELETE/TRUNCATE for every role.
--
-- Unwrapped on purpose: db-migrate.yml applies the file and its ledger row in one
-- psql single-transaction call. DDL is replay-safe through IF NOT EXISTS,
-- CREATE OR REPLACE, and DROP TRIGGER IF EXISTS before CREATE TRIGGER.

CREATE TABLE IF NOT EXISTS public.olympus_risk_policies (
    policy_id uuid PRIMARY KEY,
    method_version text NOT NULL CHECK (length(method_version) BETWEEN 1 AND 200),
    source_run_id text CHECK (
        source_run_id IS NULL OR length(source_run_id) BETWEEN 1 AND 200
    ),
    status text NOT NULL CHECK (status IN ('available', 'degraded', 'unavailable')),
    unavailable_reason text CHECK (
        unavailable_reason IS NULL OR length(unavailable_reason) BETWEEN 1 AND 500
    ),
    content_hash text NOT NULL CHECK (length(content_hash) = 64),
    effective_at timestamptz NOT NULL,
    policy_body jsonb NOT NULL CHECK (jsonb_typeof(policy_body) = 'object'),
    recorded_at timestamptz NOT NULL DEFAULT now()
);

CREATE TABLE IF NOT EXISTS public.olympus_covariance_snapshots (
    snapshot_id uuid PRIMARY KEY,
    method_version text NOT NULL CHECK (length(method_version) BETWEEN 1 AND 200),
    as_of_session date NOT NULL,
    lookback_days integer NOT NULL CHECK (lookback_days >= 1),
    status text NOT NULL CHECK (status IN ('available', 'degraded', 'unavailable')),
    unavailable_reason text CHECK (
        unavailable_reason IS NULL OR length(unavailable_reason) BETWEEN 1 AND 500
    ),
    content_hash text NOT NULL CHECK (length(content_hash) = 64),
    resolved_at timestamptz NOT NULL,
    snapshot_body jsonb NOT NULL CHECK (jsonb_typeof(snapshot_body) = 'object'),
    recorded_at timestamptz NOT NULL DEFAULT now()
);

CREATE TABLE IF NOT EXISTS public.olympus_h8_risk_run_refs (
    source_run_id text PRIMARY KEY CHECK (length(source_run_id) BETWEEN 1 AND 200),
    run_date date NOT NULL,
    policy_id uuid NOT NULL,
    snapshot_id uuid NOT NULL,
    effective_at timestamptz NOT NULL,
    recorded_at timestamptz NOT NULL DEFAULT now(),
    CONSTRAINT fk_olympus_h8_risk_run_refs_policy
        FOREIGN KEY (policy_id)
        REFERENCES public.olympus_risk_policies (policy_id),
    CONSTRAINT fk_olympus_h8_risk_run_refs_snapshot
        FOREIGN KEY (snapshot_id)
        REFERENCES public.olympus_covariance_snapshots (snapshot_id)
);

CREATE INDEX IF NOT EXISTS idx_olympus_risk_policies_effective
    ON public.olympus_risk_policies (effective_at);

CREATE INDEX IF NOT EXISTS idx_olympus_covariance_snapshots_session
    ON public.olympus_covariance_snapshots (as_of_session, resolved_at);

CREATE INDEX IF NOT EXISTS idx_olympus_h8_risk_run_refs_run_date
    ON public.olympus_h8_risk_run_refs (run_date);

ALTER TABLE public.olympus_risk_policies ENABLE ROW LEVEL SECURITY;
ALTER TABLE public.olympus_covariance_snapshots ENABLE ROW LEVEL SECURITY;
ALTER TABLE public.olympus_h8_risk_run_refs ENABLE ROW LEVEL SECURITY;

REVOKE ALL ON public.olympus_risk_policies FROM PUBLIC, anon, authenticated;
REVOKE ALL ON public.olympus_covariance_snapshots FROM PUBLIC, anon, authenticated;
REVOKE ALL ON public.olympus_h8_risk_run_refs FROM PUBLIC, anon, authenticated;

REVOKE ALL ON public.olympus_risk_policies FROM service_role;
REVOKE ALL ON public.olympus_covariance_snapshots FROM service_role;
REVOKE ALL ON public.olympus_h8_risk_run_refs FROM service_role;

GRANT SELECT, INSERT ON public.olympus_risk_policies TO service_role;
GRANT SELECT, INSERT ON public.olympus_covariance_snapshots TO service_role;
GRANT SELECT, INSERT ON public.olympus_h8_risk_run_refs TO service_role;

CREATE OR REPLACE FUNCTION public.reject_olympus_risk_policy_snapshot_mutation()
RETURNS trigger
LANGUAGE plpgsql
SET search_path = ''
AS $$
BEGIN
    RAISE EXCEPTION 'risk policy snapshot registry is append-only (#2698)'
        USING ERRCODE = '55000';
END
$$;

DROP TRIGGER IF EXISTS reject_olympus_risk_policies_mutation
    ON public.olympus_risk_policies;
CREATE TRIGGER reject_olympus_risk_policies_mutation
    BEFORE UPDATE OR DELETE ON public.olympus_risk_policies
    FOR EACH ROW EXECUTE FUNCTION public.reject_olympus_risk_policy_snapshot_mutation();
DROP TRIGGER IF EXISTS reject_olympus_risk_policies_truncate
    ON public.olympus_risk_policies;
CREATE TRIGGER reject_olympus_risk_policies_truncate
    BEFORE TRUNCATE ON public.olympus_risk_policies
    FOR EACH STATEMENT EXECUTE FUNCTION public.reject_olympus_risk_policy_snapshot_mutation();

DROP TRIGGER IF EXISTS reject_olympus_covariance_snapshots_mutation
    ON public.olympus_covariance_snapshots;
CREATE TRIGGER reject_olympus_covariance_snapshots_mutation
    BEFORE UPDATE OR DELETE ON public.olympus_covariance_snapshots
    FOR EACH ROW EXECUTE FUNCTION public.reject_olympus_risk_policy_snapshot_mutation();
DROP TRIGGER IF EXISTS reject_olympus_covariance_snapshots_truncate
    ON public.olympus_covariance_snapshots;
CREATE TRIGGER reject_olympus_covariance_snapshots_truncate
    BEFORE TRUNCATE ON public.olympus_covariance_snapshots
    FOR EACH STATEMENT EXECUTE FUNCTION public.reject_olympus_risk_policy_snapshot_mutation();

DROP TRIGGER IF EXISTS reject_olympus_h8_risk_run_refs_mutation
    ON public.olympus_h8_risk_run_refs;
CREATE TRIGGER reject_olympus_h8_risk_run_refs_mutation
    BEFORE UPDATE OR DELETE ON public.olympus_h8_risk_run_refs
    FOR EACH ROW EXECUTE FUNCTION public.reject_olympus_risk_policy_snapshot_mutation();
DROP TRIGGER IF EXISTS reject_olympus_h8_risk_run_refs_truncate
    ON public.olympus_h8_risk_run_refs;
CREATE TRIGGER reject_olympus_h8_risk_run_refs_truncate
    BEFORE TRUNCATE ON public.olympus_h8_risk_run_refs
    FOR EACH STATEMENT EXECUTE FUNCTION public.reject_olympus_risk_policy_snapshot_mutation();

REVOKE ALL ON FUNCTION public.reject_olympus_risk_policy_snapshot_mutation()
    FROM PUBLIC, anon, authenticated;

COMMENT ON TABLE public.olympus_risk_policies IS
    'Append-only resolved RiskPolicy snapshots for H8 audit (#2698 / WP6.3).';
COMMENT ON TABLE public.olympus_covariance_snapshots IS
    'Append-only canonical CovarianceSnapshot rows for H8 audit (#2698 / WP6.3).';
COMMENT ON TABLE public.olympus_h8_risk_run_refs IS
    'One ref per source_run_id binding H8 policy + covariance snapshot (#2698).';
COMMENT ON FUNCTION public.reject_olympus_risk_policy_snapshot_mutation() IS
    'Append-only guard for olympus risk policy snapshot tables (#2698).';
