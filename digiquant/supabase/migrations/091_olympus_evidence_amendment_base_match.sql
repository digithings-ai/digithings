-- 091_olympus_evidence_amendment_base_match.sql
--
-- WP11.1 review follow-up (#2895): enforce that an evidence-bundle amendment's
-- base_bundle_id matches the linked missing-fact request's base_bundle_id.
-- Migration 090 FKs alone allow a cross-linked insert; the in-memory
-- EvidenceBundleStore already rejects that case.
--
-- Additive only — does not rewrite 090. Unwrapped for db-migrate.yml
-- single-transaction apply (IF NOT EXISTS / CREATE OR REPLACE /
-- DROP TRIGGER IF EXISTS).

CREATE OR REPLACE FUNCTION public.reject_olympus_evidence_amendment_base_mismatch()
RETURNS trigger
LANGUAGE plpgsql
SET search_path = ''
AS $$
DECLARE
    request_base uuid;
BEGIN
    SELECT r.base_bundle_id
      INTO request_base
      FROM public.olympus_missing_fact_requests AS r
     WHERE r.request_id = NEW.missing_fact_request_id;

    IF request_base IS NULL THEN
        RAISE EXCEPTION 'missing-fact request % not found for amendment',
            NEW.missing_fact_request_id
            USING ERRCODE = '23503';
    END IF;

    IF request_base <> NEW.base_bundle_id THEN
        RAISE EXCEPTION
            'amendment base_bundle_id must match missing-fact request base (#2895)'
            USING ERRCODE = '23514';
    END IF;

    RETURN NEW;
END;
$$;

DROP TRIGGER IF EXISTS reject_olympus_evidence_amendment_base_mismatch
    ON public.olympus_evidence_bundle_amendments;
CREATE TRIGGER reject_olympus_evidence_amendment_base_mismatch
    BEFORE INSERT OR UPDATE ON public.olympus_evidence_bundle_amendments
    FOR EACH ROW EXECUTE FUNCTION public.reject_olympus_evidence_amendment_base_mismatch();
