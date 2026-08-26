-- 083_olympus_pretrade_risk_reports.sql
--
-- Private append-only PreTradeRiskReport registry (#2754 / WP9.4).
--
-- H9 validates report identity (content hash, final-book fingerprint, bundle
-- hash) against the committed book, then INSERT-only persists the hash-bound
-- report. H9 never recomputes the report. Exact retry (same report_id + same
-- report_content_hash) is a no-op; content conflict never UPDATE/DELETE.
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

CREATE TABLE IF NOT EXISTS public.olympus_pretrade_risk_reports (
    report_id uuid PRIMARY KEY,
    source_run_id text NOT NULL CHECK (length(source_run_id) BETWEEN 1 AND 200),
    session_date date NOT NULL,
    status text NOT NULL CHECK (status IN ('available', 'degraded', 'unavailable')),
    unavailable_reason text CHECK (
        unavailable_reason IS NULL OR length(unavailable_reason) BETWEEN 1 AND 500
    ),
    report_content_hash text NOT NULL CHECK (length(report_content_hash) = 64),
    allocation_input_bundle_hash text NOT NULL CHECK (
        length(allocation_input_bundle_hash) = 64
    ),
    final_book_weights_fingerprint text NOT NULL CHECK (
        length(final_book_weights_fingerprint) BETWEEN 1 AND 128
    ),
    ledger_commit_id uuid,
    report_body jsonb NOT NULL CHECK (jsonb_typeof(report_body) = 'object'),
    recorded_at timestamptz NOT NULL DEFAULT now()
);

CREATE INDEX IF NOT EXISTS idx_olympus_pretrade_risk_reports_session
    ON public.olympus_pretrade_risk_reports (session_date, recorded_at);

CREATE INDEX IF NOT EXISTS idx_olympus_pretrade_risk_reports_run
    ON public.olympus_pretrade_risk_reports (source_run_id);

CREATE INDEX IF NOT EXISTS idx_olympus_pretrade_risk_reports_book_fp
    ON public.olympus_pretrade_risk_reports (final_book_weights_fingerprint);

ALTER TABLE public.olympus_pretrade_risk_reports ENABLE ROW LEVEL SECURITY;

REVOKE ALL ON public.olympus_pretrade_risk_reports FROM PUBLIC, anon, authenticated;
REVOKE ALL ON public.olympus_pretrade_risk_reports FROM service_role;
GRANT SELECT, INSERT ON public.olympus_pretrade_risk_reports TO service_role;

CREATE OR REPLACE FUNCTION public.reject_olympus_pretrade_risk_report_mutation()
RETURNS trigger
LANGUAGE plpgsql
SET search_path = ''
AS $$
BEGIN
    RAISE EXCEPTION 'pre-trade risk report registry is append-only (#2754)'
        USING ERRCODE = '55000';
END
$$;

DROP TRIGGER IF EXISTS reject_olympus_pretrade_risk_reports_mutation
    ON public.olympus_pretrade_risk_reports;
CREATE TRIGGER reject_olympus_pretrade_risk_reports_mutation
    BEFORE UPDATE OR DELETE ON public.olympus_pretrade_risk_reports
    FOR EACH ROW EXECUTE FUNCTION public.reject_olympus_pretrade_risk_report_mutation();
DROP TRIGGER IF EXISTS reject_olympus_pretrade_risk_reports_truncate
    ON public.olympus_pretrade_risk_reports;
CREATE TRIGGER reject_olympus_pretrade_risk_reports_truncate
    BEFORE TRUNCATE ON public.olympus_pretrade_risk_reports
    FOR EACH STATEMENT EXECUTE FUNCTION public.reject_olympus_pretrade_risk_report_mutation();

REVOKE ALL ON FUNCTION public.reject_olympus_pretrade_risk_report_mutation()
    FROM PUBLIC, anon, authenticated;

COMMENT ON TABLE public.olympus_pretrade_risk_reports IS
    'Append-only hash-bound PreTradeRiskReport rows for H9 audit (#2754 / WP9.4).';
COMMENT ON FUNCTION public.reject_olympus_pretrade_risk_report_mutation() IS
    'Append-only guard for olympus_pretrade_risk_reports (#2754).';
