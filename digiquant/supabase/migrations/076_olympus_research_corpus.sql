-- 076_olympus_research_corpus.sql
--
-- Track B WP12-class shared research corpus (#2613): private, append-only
-- tenant-agnostic pins keyed as theme: / asset: / segment:. House writes the
-- default corpus; overlays may only publish-if-missing (application layer).
-- No per-user fork columns and no graph forks.
--
-- Privacy: research corpus is shared / anonymizable (no portfolio fields).
-- RLS enabled with zero policies; PUBLIC/anon/authenticated fully revoked;
-- service_role reset then SELECT+INSERT only. Append-only triggers reject
-- UPDATE/DELETE/TRUNCATE.
--
-- Unwrapped on purpose: db-migrate.yml applies the file and its ledger row in
-- one psql single-transaction call.

CREATE TABLE IF NOT EXISTS public.olympus_research_corpus (
    id uuid PRIMARY KEY,
    corpus_key text NOT NULL CHECK (
        corpus_key ~ '^(theme|asset|segment):[a-z0-9][a-z0-9._/-]{0,198}$'
    ),
    schema_version integer NOT NULL CHECK (schema_version >= 1),
    writer_role text NOT NULL CHECK (writer_role IN ('house', 'overlay_request')),
    label text NOT NULL CHECK (length(label) BETWEEN 1 AND 200),
    summary text NOT NULL DEFAULT '' CHECK (length(summary) <= 4000),
    payload jsonb NOT NULL DEFAULT '{}'::jsonb,
    recorded_at timestamptz NOT NULL DEFAULT now(),
    CONSTRAINT chk_olympus_research_corpus_no_tenant_payload CHECK (
        NOT (payload ?| ARRAY['user_id', 'profile_id', 'tenant_id', 'profile_key'])
    )
);

COMMENT ON TABLE public.olympus_research_corpus IS
  'Shared Olympus research corpus pins (#2613). Tenant-agnostic keys '
  '(theme:/asset:/segment:). Append-only; publish-if-missing at application '
  'layer. No per-user research forks.';

CREATE UNIQUE INDEX IF NOT EXISTS uq_olympus_research_corpus_key
    ON public.olympus_research_corpus (corpus_key);

CREATE INDEX IF NOT EXISTS idx_olympus_research_corpus_kind_recorded
    ON public.olympus_research_corpus (writer_role, recorded_at DESC);

CREATE OR REPLACE FUNCTION public.reject_olympus_research_corpus_mutation()
RETURNS trigger
LANGUAGE plpgsql
AS $$
BEGIN
    RAISE EXCEPTION 'olympus_research_corpus is append-only (#2613); use publish-if-missing INSERT only'
        USING ERRCODE = '55000';
END;
$$;

ALTER TABLE public.olympus_research_corpus ENABLE ROW LEVEL SECURITY;

REVOKE ALL ON public.olympus_research_corpus FROM PUBLIC, anon, authenticated;
REVOKE ALL ON public.olympus_research_corpus FROM service_role;
GRANT SELECT, INSERT ON public.olympus_research_corpus TO service_role;

DROP TRIGGER IF EXISTS reject_olympus_research_corpus_mutation
    ON public.olympus_research_corpus;
CREATE TRIGGER reject_olympus_research_corpus_mutation
    BEFORE UPDATE OR DELETE ON public.olympus_research_corpus
    FOR EACH ROW EXECUTE FUNCTION public.reject_olympus_research_corpus_mutation();

DROP TRIGGER IF EXISTS reject_olympus_research_corpus_truncate
    ON public.olympus_research_corpus;
CREATE TRIGGER reject_olympus_research_corpus_truncate
    BEFORE TRUNCATE ON public.olympus_research_corpus
    FOR EACH STATEMENT EXECUTE FUNCTION public.reject_olympus_research_corpus_mutation();
