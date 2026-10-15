-- 090_olympus_evidence_bundles.sql
--
-- Phase 3 WP11.1 private append-only ticker evidence bundles (#2844).
--
-- Persists frozen H5 base TickerEvidenceBundle rows plus append-only
-- MissingFactRequest / EvidenceBundleAmendment vocabulary. H6 may only
-- supplement a named missing fact — never mutate the base. Distinct from
-- WP12 research-state leaves (EvidenceRecord etc.); bundle rows cite
-- state_version_id + evidence_ids for lineage.
--
-- Dark launch: no public base view, no historical backfill, no H6 selection
-- cutover (WP11.3+). Application store:
-- digiquant.olympus.research_retrieval.store.EvidenceBundleStore.
--
-- Privacy: RLS enabled with zero policies; PUBLIC/anon/authenticated fully
-- revoked; service_role reset then SELECT+INSERT only. Append-only triggers
-- reject UPDATE/DELETE/TRUNCATE for every role.
--
-- Unwrapped on purpose: db-migrate.yml applies the file and its ledger row in
-- one psql single-transaction call. DDL is replay-safe through IF NOT EXISTS,
-- CREATE OR REPLACE, and DROP TRIGGER IF EXISTS before CREATE TRIGGER.

CREATE TABLE IF NOT EXISTS public.olympus_ticker_evidence_bundles (
    bundle_id uuid PRIMARY KEY,
    ticker text NOT NULL CHECK (length(ticker) BETWEEN 1 AND 500),
    source_run_id text NOT NULL CHECK (length(source_run_id) BETWEEN 1 AND 500),
    attempt_id text NOT NULL CHECK (length(attempt_id) BETWEEN 1 AND 500),
    state_version_id uuid NOT NULL,
    content_hash text NOT NULL CHECK (length(content_hash) = 64),
    source text NOT NULL CHECK (length(source) BETWEEN 1 AND 500),
    event_time timestamptz NOT NULL,
    effective_as_of timestamptz NOT NULL,
    known_at timestamptz NOT NULL,
    recorded_at timestamptz NOT NULL,
    schema_version integer NOT NULL CHECK (schema_version >= 1),
    payload jsonb NOT NULL CHECK (jsonb_typeof(payload) = 'object'),
    CONSTRAINT uq_olympus_ticker_evidence_bundles_run_ticker_content
        UNIQUE (source_run_id, ticker, content_hash),
    CONSTRAINT uq_olympus_ticker_evidence_bundles_run_ticker
        UNIQUE (source_run_id, ticker)
);

CREATE TABLE IF NOT EXISTS public.olympus_missing_fact_requests (
    request_id uuid PRIMARY KEY,
    base_bundle_id uuid NOT NULL,
    ticker text NOT NULL CHECK (length(ticker) BETWEEN 1 AND 500),
    fact_key text NOT NULL CHECK (length(fact_key) BETWEEN 1 AND 500),
    content_hash text NOT NULL CHECK (length(content_hash) = 64),
    event_time timestamptz NOT NULL,
    effective_as_of timestamptz NOT NULL,
    known_at timestamptz NOT NULL,
    recorded_at timestamptz NOT NULL,
    schema_version integer NOT NULL CHECK (schema_version >= 1),
    payload jsonb NOT NULL CHECK (jsonb_typeof(payload) = 'object'),
    CONSTRAINT fk_olympus_missing_fact_requests_base
        FOREIGN KEY (base_bundle_id)
        REFERENCES public.olympus_ticker_evidence_bundles (bundle_id)
);

CREATE TABLE IF NOT EXISTS public.olympus_evidence_bundle_amendments (
    amendment_id uuid PRIMARY KEY,
    base_bundle_id uuid NOT NULL,
    missing_fact_request_id uuid NOT NULL,
    ticker text NOT NULL CHECK (length(ticker) BETWEEN 1 AND 500),
    content_hash text NOT NULL CHECK (length(content_hash) = 64),
    source text NOT NULL CHECK (length(source) BETWEEN 1 AND 500),
    event_time timestamptz NOT NULL,
    effective_as_of timestamptz NOT NULL,
    known_at timestamptz NOT NULL,
    recorded_at timestamptz NOT NULL,
    schema_version integer NOT NULL CHECK (schema_version >= 1),
    payload jsonb NOT NULL CHECK (jsonb_typeof(payload) = 'object'),
    CONSTRAINT fk_olympus_evidence_bundle_amendments_base
        FOREIGN KEY (base_bundle_id)
        REFERENCES public.olympus_ticker_evidence_bundles (bundle_id),
    CONSTRAINT fk_olympus_evidence_bundle_amendments_request
        FOREIGN KEY (missing_fact_request_id)
        REFERENCES public.olympus_missing_fact_requests (request_id)
);

CREATE INDEX IF NOT EXISTS idx_olympus_ticker_evidence_bundles_known
    ON public.olympus_ticker_evidence_bundles (known_at);

CREATE INDEX IF NOT EXISTS idx_olympus_ticker_evidence_bundles_state
    ON public.olympus_ticker_evidence_bundles (state_version_id);

CREATE INDEX IF NOT EXISTS idx_olympus_missing_fact_requests_base
    ON public.olympus_missing_fact_requests (base_bundle_id);

CREATE INDEX IF NOT EXISTS idx_olympus_evidence_bundle_amendments_base
    ON public.olympus_evidence_bundle_amendments (base_bundle_id);

ALTER TABLE public.olympus_ticker_evidence_bundles ENABLE ROW LEVEL SECURITY;
ALTER TABLE public.olympus_missing_fact_requests ENABLE ROW LEVEL SECURITY;
ALTER TABLE public.olympus_evidence_bundle_amendments ENABLE ROW LEVEL SECURITY;

REVOKE ALL ON public.olympus_ticker_evidence_bundles FROM PUBLIC, anon, authenticated;
REVOKE ALL ON public.olympus_missing_fact_requests FROM PUBLIC, anon, authenticated;
REVOKE ALL ON public.olympus_evidence_bundle_amendments FROM PUBLIC, anon, authenticated;

REVOKE ALL ON public.olympus_ticker_evidence_bundles FROM service_role;
REVOKE ALL ON public.olympus_missing_fact_requests FROM service_role;
REVOKE ALL ON public.olympus_evidence_bundle_amendments FROM service_role;

GRANT SELECT, INSERT ON public.olympus_ticker_evidence_bundles TO service_role;
GRANT SELECT, INSERT ON public.olympus_missing_fact_requests TO service_role;
GRANT SELECT, INSERT ON public.olympus_evidence_bundle_amendments TO service_role;

CREATE OR REPLACE FUNCTION public.reject_olympus_evidence_bundle_mutation()
RETURNS trigger
LANGUAGE plpgsql
SET search_path = ''
AS $$
BEGIN
    RAISE EXCEPTION 'evidence bundle store is append-only (#2844)'
        USING ERRCODE = '55000';
END
$$;

DROP TRIGGER IF EXISTS reject_olympus_ticker_evidence_bundles_mutation
    ON public.olympus_ticker_evidence_bundles;
CREATE TRIGGER reject_olympus_ticker_evidence_bundles_mutation
    BEFORE UPDATE OR DELETE ON public.olympus_ticker_evidence_bundles
    FOR EACH ROW EXECUTE FUNCTION public.reject_olympus_evidence_bundle_mutation();
DROP TRIGGER IF EXISTS reject_olympus_ticker_evidence_bundles_truncate
    ON public.olympus_ticker_evidence_bundles;
CREATE TRIGGER reject_olympus_ticker_evidence_bundles_truncate
    BEFORE TRUNCATE ON public.olympus_ticker_evidence_bundles
    FOR EACH STATEMENT EXECUTE FUNCTION public.reject_olympus_evidence_bundle_mutation();

DROP TRIGGER IF EXISTS reject_olympus_missing_fact_requests_mutation
    ON public.olympus_missing_fact_requests;
CREATE TRIGGER reject_olympus_missing_fact_requests_mutation
    BEFORE UPDATE OR DELETE ON public.olympus_missing_fact_requests
    FOR EACH ROW EXECUTE FUNCTION public.reject_olympus_evidence_bundle_mutation();
DROP TRIGGER IF EXISTS reject_olympus_missing_fact_requests_truncate
    ON public.olympus_missing_fact_requests;
CREATE TRIGGER reject_olympus_missing_fact_requests_truncate
    BEFORE TRUNCATE ON public.olympus_missing_fact_requests
    FOR EACH STATEMENT EXECUTE FUNCTION public.reject_olympus_evidence_bundle_mutation();

DROP TRIGGER IF EXISTS reject_olympus_evidence_bundle_amendments_mutation
    ON public.olympus_evidence_bundle_amendments;
CREATE TRIGGER reject_olympus_evidence_bundle_amendments_mutation
    BEFORE UPDATE OR DELETE ON public.olympus_evidence_bundle_amendments
    FOR EACH ROW EXECUTE FUNCTION public.reject_olympus_evidence_bundle_mutation();
DROP TRIGGER IF EXISTS reject_olympus_evidence_bundle_amendments_truncate
    ON public.olympus_evidence_bundle_amendments;
CREATE TRIGGER reject_olympus_evidence_bundle_amendments_truncate
    BEFORE TRUNCATE ON public.olympus_evidence_bundle_amendments
    FOR EACH STATEMENT EXECUTE FUNCTION public.reject_olympus_evidence_bundle_mutation();
