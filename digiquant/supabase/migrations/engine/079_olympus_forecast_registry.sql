-- 079_olympus_forecast_registry.sql
--
-- Private append-only prospective forecast lineage (#2663 / WP4.6).
--
-- Stores immutable H5 ForecastAssessment bases and H6 ForecastAmendment records
-- independently of rendered documents. Written prospectively through H9 after
-- portfolio booking — registry failure is fail-soft and cannot rebook.
--
-- No historical INSERT ... SELECT. No prompt/reasoning bodies. No public base view.
-- Outcome/calibration writers are WP5.
--
-- Privacy: RLS enabled with zero policies; PUBLIC/anon/authenticated fully revoked;
-- service_role reset then SELECT+INSERT only. Append-only triggers reject
-- UPDATE/DELETE/TRUNCATE for every role.
--
-- Unwrapped on purpose: db-migrate.yml applies the file and its ledger row in one
-- psql single-transaction call. DDL is replay-safe through IF NOT EXISTS,
-- CREATE OR REPLACE, and DROP TRIGGER IF EXISTS before CREATE TRIGGER.

CREATE TABLE IF NOT EXISTS public.olympus_forecast_assessments (
    forecast_id uuid PRIMARY KEY,
    ticker text NOT NULL CHECK (length(ticker) BETWEEN 1 AND 32),
    source_run_id text NOT NULL CHECK (length(source_run_id) BETWEEN 1 AND 200),
    provider_invocation_id text NOT NULL CHECK (
        length(provider_invocation_id) BETWEEN 1 AND 200
    ),
    prompt_version text NOT NULL CHECK (length(prompt_version) BETWEEN 1 AND 200),
    artifact_version text NOT NULL CHECK (length(artifact_version) BETWEEN 1 AND 200),
    terms jsonb NOT NULL CHECK (jsonb_typeof(terms) = 'object'),
    price_anchor jsonb NOT NULL CHECK (jsonb_typeof(price_anchor) = 'object'),
    content_hash text NOT NULL CHECK (length(content_hash) = 64),
    effective_at timestamptz NOT NULL,
    known_at timestamptz NOT NULL,
    recorded_at timestamptz NOT NULL DEFAULT now()
);

CREATE TABLE IF NOT EXISTS public.olympus_forecast_amendments (
    amendment_id uuid PRIMARY KEY,
    base_forecast_id uuid NOT NULL,
    supersedes_amendment_id uuid,
    ticker text NOT NULL CHECK (length(ticker) BETWEEN 1 AND 32),
    source_run_id text NOT NULL CHECK (length(source_run_id) BETWEEN 1 AND 200),
    provider_invocation_id text NOT NULL CHECK (
        length(provider_invocation_id) BETWEEN 1 AND 200
    ),
    reason text NOT NULL CHECK (length(reason) BETWEEN 1 AND 2000),
    terms jsonb NOT NULL CHECK (jsonb_typeof(terms) = 'object'),
    new_evidence_ids text[] NOT NULL DEFAULT '{}'::text[],
    contradiction_ids text[] NOT NULL DEFAULT '{}'::text[],
    content_hash text NOT NULL CHECK (length(content_hash) = 64),
    effective_at timestamptz NOT NULL,
    known_at timestamptz NOT NULL,
    recorded_at timestamptz NOT NULL DEFAULT now(),
    CONSTRAINT fk_olympus_forecast_amendments_base
        FOREIGN KEY (base_forecast_id)
        REFERENCES public.olympus_forecast_assessments (forecast_id),
    CONSTRAINT fk_olympus_forecast_amendments_supersedes
        FOREIGN KEY (supersedes_amendment_id)
        REFERENCES public.olympus_forecast_amendments (amendment_id),
    CONSTRAINT chk_olympus_forecast_amendments_no_self_supersede
        CHECK (
            supersedes_amendment_id IS NULL
            OR supersedes_amendment_id <> amendment_id
        )
);

CREATE INDEX IF NOT EXISTS idx_olympus_forecast_assessments_ticker_known
    ON public.olympus_forecast_assessments (ticker, known_at);

CREATE INDEX IF NOT EXISTS idx_olympus_forecast_assessments_run
    ON public.olympus_forecast_assessments (source_run_id);

CREATE INDEX IF NOT EXISTS idx_olympus_forecast_amendments_base_known
    ON public.olympus_forecast_amendments (base_forecast_id, known_at);

CREATE INDEX IF NOT EXISTS idx_olympus_forecast_amendments_ticker_known
    ON public.olympus_forecast_amendments (ticker, known_at);

ALTER TABLE public.olympus_forecast_assessments ENABLE ROW LEVEL SECURITY;
ALTER TABLE public.olympus_forecast_amendments ENABLE ROW LEVEL SECURITY;

REVOKE ALL ON public.olympus_forecast_assessments FROM PUBLIC, anon, authenticated;
REVOKE ALL ON public.olympus_forecast_amendments FROM PUBLIC, anon, authenticated;

REVOKE ALL ON public.olympus_forecast_assessments FROM service_role;
REVOKE ALL ON public.olympus_forecast_amendments FROM service_role;

GRANT SELECT, INSERT ON public.olympus_forecast_assessments TO service_role;
GRANT SELECT, INSERT ON public.olympus_forecast_amendments TO service_role;

CREATE OR REPLACE FUNCTION public.reject_olympus_forecast_registry_mutation()
RETURNS trigger
LANGUAGE plpgsql
SET search_path = ''
AS $$
BEGIN
    RAISE EXCEPTION 'forecast registry is append-only (#2663)'
        USING ERRCODE = '55000';
END
$$;

DROP TRIGGER IF EXISTS reject_olympus_forecast_assessments_mutation
    ON public.olympus_forecast_assessments;
CREATE TRIGGER reject_olympus_forecast_assessments_mutation
    BEFORE UPDATE OR DELETE ON public.olympus_forecast_assessments
    FOR EACH ROW EXECUTE FUNCTION public.reject_olympus_forecast_registry_mutation();
DROP TRIGGER IF EXISTS reject_olympus_forecast_assessments_truncate
    ON public.olympus_forecast_assessments;
CREATE TRIGGER reject_olympus_forecast_assessments_truncate
    BEFORE TRUNCATE ON public.olympus_forecast_assessments
    FOR EACH STATEMENT EXECUTE FUNCTION public.reject_olympus_forecast_registry_mutation();

DROP TRIGGER IF EXISTS reject_olympus_forecast_amendments_mutation
    ON public.olympus_forecast_amendments;
CREATE TRIGGER reject_olympus_forecast_amendments_mutation
    BEFORE UPDATE OR DELETE ON public.olympus_forecast_amendments
    FOR EACH ROW EXECUTE FUNCTION public.reject_olympus_forecast_registry_mutation();
DROP TRIGGER IF EXISTS reject_olympus_forecast_amendments_truncate
    ON public.olympus_forecast_amendments;
CREATE TRIGGER reject_olympus_forecast_amendments_truncate
    BEFORE TRUNCATE ON public.olympus_forecast_amendments
    FOR EACH STATEMENT EXECUTE FUNCTION public.reject_olympus_forecast_registry_mutation();

REVOKE ALL ON FUNCTION public.reject_olympus_forecast_registry_mutation()
    FROM PUBLIC, anon, authenticated;

COMMENT ON TABLE public.olympus_forecast_assessments IS
    'Private append-only H5 ForecastAssessment bases (#2663 / WP4.6). '
    'Prospective writes only; no prompt bodies; no public view.';

COMMENT ON TABLE public.olympus_forecast_amendments IS
    'Private append-only H6 ForecastAmendment records (#2663 / WP4.6). '
    'Supersession is append-only; never rewrites the base assessment.';

COMMENT ON FUNCTION public.reject_olympus_forecast_registry_mutation() IS
    'Rejects UPDATE, DELETE, and TRUNCATE on forecast registry tables.';
