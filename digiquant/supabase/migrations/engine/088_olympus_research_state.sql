-- 088_olympus_research_state.sql
--
-- Phase 3 WP12.2 private append-only research-state store (#2854).
--
-- Persists frozen WP12.1 contracts (EvidenceRecord, BeliefVersion,
-- ExpectedEventVersion, ResearchPatch, LegacyDocumentRef, ResearchStateVersion,
-- ResearchStatePin) as exact-version structured research memory. Distinct from
-- Track B olympus_research_corpus (theme/asset/segment identity pins).
--
-- Dark launch: no public base view, no historical backfill, no prose parsing.
-- Application store: digiquant.olympus.research_retrieval.store.
--
-- Privacy: RLS enabled with zero policies; PUBLIC/anon/authenticated fully
-- revoked; service_role reset then SELECT+INSERT only. Append-only triggers
-- reject UPDATE/DELETE/TRUNCATE for every role.
--
-- Unwrapped on purpose: db-migrate.yml applies the file and its ledger row in
-- one psql single-transaction call. DDL is replay-safe through IF NOT EXISTS,
-- CREATE OR REPLACE, and DROP TRIGGER IF EXISTS before CREATE TRIGGER.

CREATE TABLE IF NOT EXISTS public.olympus_research_evidence (
    evidence_id uuid PRIMARY KEY,
    source text NOT NULL CHECK (length(source) BETWEEN 1 AND 500),
    authority text NOT NULL CHECK (length(authority) BETWEEN 1 AND 500),
    content_hash text NOT NULL CHECK (length(content_hash) = 64),
    supersedes_evidence_id uuid,
    event_time timestamptz NOT NULL,
    effective_as_of timestamptz NOT NULL,
    known_at timestamptz NOT NULL,
    recorded_at timestamptz NOT NULL,
    schema_version integer NOT NULL CHECK (schema_version >= 1),
    payload jsonb NOT NULL CHECK (jsonb_typeof(payload) = 'object'),
    CONSTRAINT fk_olympus_research_evidence_supersedes
        FOREIGN KEY (supersedes_evidence_id)
        REFERENCES public.olympus_research_evidence (evidence_id),
    CONSTRAINT chk_olympus_research_evidence_no_self_supersede
        CHECK (
            supersedes_evidence_id IS NULL
            OR supersedes_evidence_id <> evidence_id
        )
);

CREATE TABLE IF NOT EXISTS public.olympus_research_belief_versions (
    belief_version_id uuid PRIMARY KEY,
    belief_id uuid NOT NULL,
    content_hash text NOT NULL CHECK (length(content_hash) = 64),
    status text NOT NULL CHECK (length(status) BETWEEN 1 AND 64),
    supersedes_version_id uuid,
    event_time timestamptz NOT NULL,
    effective_as_of timestamptz NOT NULL,
    known_at timestamptz NOT NULL,
    recorded_at timestamptz NOT NULL,
    schema_version integer NOT NULL CHECK (schema_version >= 1),
    payload jsonb NOT NULL CHECK (jsonb_typeof(payload) = 'object'),
    CONSTRAINT fk_olympus_research_belief_versions_supersedes
        FOREIGN KEY (supersedes_version_id)
        REFERENCES public.olympus_research_belief_versions (belief_version_id),
    CONSTRAINT chk_olympus_research_belief_versions_no_self_supersede
        CHECK (
            supersedes_version_id IS NULL
            OR supersedes_version_id <> belief_version_id
        )
);

CREATE TABLE IF NOT EXISTS public.olympus_research_expected_event_versions (
    expected_event_version_id uuid PRIMARY KEY,
    expected_event_id uuid NOT NULL,
    content_hash text NOT NULL CHECK (length(content_hash) = 64),
    status text NOT NULL CHECK (length(status) BETWEEN 1 AND 64),
    supersedes_version_id uuid,
    event_time timestamptz NOT NULL,
    effective_as_of timestamptz NOT NULL,
    known_at timestamptz NOT NULL,
    recorded_at timestamptz NOT NULL,
    schema_version integer NOT NULL CHECK (schema_version >= 1),
    payload jsonb NOT NULL CHECK (jsonb_typeof(payload) = 'object'),
    CONSTRAINT fk_olympus_research_expected_event_versions_supersedes
        FOREIGN KEY (supersedes_version_id)
        REFERENCES public.olympus_research_expected_event_versions (
            expected_event_version_id
        ),
    CONSTRAINT chk_olympus_research_expected_event_versions_no_self_supersede
        CHECK (
            supersedes_version_id IS NULL
            OR supersedes_version_id <> expected_event_version_id
        )
);

CREATE TABLE IF NOT EXISTS public.olympus_research_patches (
    patch_id uuid PRIMARY KEY,
    target_kind text NOT NULL CHECK (length(target_kind) BETWEEN 1 AND 64),
    target_id text NOT NULL CHECK (length(target_id) BETWEEN 1 AND 500),
    content_hash text NOT NULL CHECK (length(content_hash) = 64),
    supersedes_patch_id uuid,
    event_time timestamptz NOT NULL,
    effective_as_of timestamptz NOT NULL,
    known_at timestamptz NOT NULL,
    recorded_at timestamptz NOT NULL,
    schema_version integer NOT NULL CHECK (schema_version >= 1),
    payload jsonb NOT NULL CHECK (jsonb_typeof(payload) = 'object'),
    CONSTRAINT fk_olympus_research_patches_supersedes
        FOREIGN KEY (supersedes_patch_id)
        REFERENCES public.olympus_research_patches (patch_id),
    CONSTRAINT chk_olympus_research_patches_no_self_supersede
        CHECK (
            supersedes_patch_id IS NULL
            OR supersedes_patch_id <> patch_id
        )
);

CREATE TABLE IF NOT EXISTS public.olympus_research_legacy_refs (
    legacy_ref_id uuid PRIMARY KEY,
    document_key text NOT NULL CHECK (length(document_key) BETWEEN 1 AND 500),
    as_of_date text NOT NULL CHECK (length(as_of_date) BETWEEN 1 AND 32),
    source_table text NOT NULL CHECK (length(source_table) BETWEEN 1 AND 200),
    source_hash text NOT NULL CHECK (length(source_hash) BETWEEN 1 AND 128),
    -- Inventory only: known_at must stay NULL so strict readers exclude these rows.
    known_at timestamptz,
    legacy_manifest_only boolean NOT NULL DEFAULT true
        CHECK (legacy_manifest_only IS TRUE),
    payload jsonb NOT NULL CHECK (jsonb_typeof(payload) = 'object'),
    CONSTRAINT chk_olympus_research_legacy_refs_null_known
        CHECK (known_at IS NULL)
);

CREATE TABLE IF NOT EXISTS public.olympus_research_state_versions (
    state_version_id uuid PRIMARY KEY,
    parent_state_version_id uuid,
    manifest_content_hash text NOT NULL CHECK (length(manifest_content_hash) = 64),
    content_hash text NOT NULL CHECK (length(content_hash) = 64),
    event_time timestamptz NOT NULL,
    effective_as_of timestamptz NOT NULL,
    known_at timestamptz NOT NULL,
    recorded_at timestamptz NOT NULL,
    schema_version integer NOT NULL CHECK (schema_version >= 1),
    payload jsonb NOT NULL CHECK (jsonb_typeof(payload) = 'object'),
    CONSTRAINT fk_olympus_research_state_versions_parent
        FOREIGN KEY (parent_state_version_id)
        REFERENCES public.olympus_research_state_versions (state_version_id),
    CONSTRAINT chk_olympus_research_state_versions_no_self_parent
        CHECK (
            parent_state_version_id IS NULL
            OR parent_state_version_id <> state_version_id
        )
);

CREATE TABLE IF NOT EXISTS public.olympus_research_state_pins (
    run_id text NOT NULL CHECK (length(run_id) BETWEEN 1 AND 500),
    attempt_id text NOT NULL CHECK (length(attempt_id) BETWEEN 1 AND 500),
    state_version_id uuid NOT NULL,
    knowledge_cutoff_at timestamptz NOT NULL,
    requested_as_of timestamptz NOT NULL,
    pinned_at timestamptz NOT NULL,
    payload jsonb NOT NULL CHECK (jsonb_typeof(payload) = 'object'),
    PRIMARY KEY (run_id, attempt_id),
    CONSTRAINT fk_olympus_research_state_pins_version
        FOREIGN KEY (state_version_id)
        REFERENCES public.olympus_research_state_versions (state_version_id)
);

CREATE INDEX IF NOT EXISTS idx_olympus_research_evidence_known
    ON public.olympus_research_evidence (known_at);

CREATE INDEX IF NOT EXISTS idx_olympus_research_belief_versions_known
    ON public.olympus_research_belief_versions (belief_id, known_at);

CREATE INDEX IF NOT EXISTS idx_olympus_research_expected_event_versions_known
    ON public.olympus_research_expected_event_versions (expected_event_id, known_at);

CREATE INDEX IF NOT EXISTS idx_olympus_research_patches_known
    ON public.olympus_research_patches (known_at);

CREATE INDEX IF NOT EXISTS idx_olympus_research_state_versions_as_of
    ON public.olympus_research_state_versions (effective_as_of, known_at);

CREATE INDEX IF NOT EXISTS idx_olympus_research_state_versions_parent
    ON public.olympus_research_state_versions (parent_state_version_id);

CREATE INDEX IF NOT EXISTS idx_olympus_research_state_pins_version
    ON public.olympus_research_state_pins (state_version_id);

ALTER TABLE public.olympus_research_evidence ENABLE ROW LEVEL SECURITY;
ALTER TABLE public.olympus_research_belief_versions ENABLE ROW LEVEL SECURITY;
ALTER TABLE public.olympus_research_expected_event_versions ENABLE ROW LEVEL SECURITY;
ALTER TABLE public.olympus_research_patches ENABLE ROW LEVEL SECURITY;
ALTER TABLE public.olympus_research_legacy_refs ENABLE ROW LEVEL SECURITY;
ALTER TABLE public.olympus_research_state_versions ENABLE ROW LEVEL SECURITY;
ALTER TABLE public.olympus_research_state_pins ENABLE ROW LEVEL SECURITY;

REVOKE ALL ON public.olympus_research_evidence FROM PUBLIC, anon, authenticated;
REVOKE ALL ON public.olympus_research_belief_versions FROM PUBLIC, anon, authenticated;
REVOKE ALL ON public.olympus_research_expected_event_versions FROM PUBLIC, anon, authenticated;
REVOKE ALL ON public.olympus_research_patches FROM PUBLIC, anon, authenticated;
REVOKE ALL ON public.olympus_research_legacy_refs FROM PUBLIC, anon, authenticated;
REVOKE ALL ON public.olympus_research_state_versions FROM PUBLIC, anon, authenticated;
REVOKE ALL ON public.olympus_research_state_pins FROM PUBLIC, anon, authenticated;

REVOKE ALL ON public.olympus_research_evidence FROM service_role;
REVOKE ALL ON public.olympus_research_belief_versions FROM service_role;
REVOKE ALL ON public.olympus_research_expected_event_versions FROM service_role;
REVOKE ALL ON public.olympus_research_patches FROM service_role;
REVOKE ALL ON public.olympus_research_legacy_refs FROM service_role;
REVOKE ALL ON public.olympus_research_state_versions FROM service_role;
REVOKE ALL ON public.olympus_research_state_pins FROM service_role;

GRANT SELECT, INSERT ON public.olympus_research_evidence TO service_role;
GRANT SELECT, INSERT ON public.olympus_research_belief_versions TO service_role;
GRANT SELECT, INSERT ON public.olympus_research_expected_event_versions TO service_role;
GRANT SELECT, INSERT ON public.olympus_research_patches TO service_role;
GRANT SELECT, INSERT ON public.olympus_research_legacy_refs TO service_role;
GRANT SELECT, INSERT ON public.olympus_research_state_versions TO service_role;
GRANT SELECT, INSERT ON public.olympus_research_state_pins TO service_role;

CREATE OR REPLACE FUNCTION public.reject_olympus_research_state_mutation()
RETURNS trigger
LANGUAGE plpgsql
SET search_path = ''
AS $$
BEGIN
    RAISE EXCEPTION 'research state store is append-only (#2854)'
        USING ERRCODE = '55000';
END
$$;

DROP TRIGGER IF EXISTS reject_olympus_research_evidence_mutation
    ON public.olympus_research_evidence;
CREATE TRIGGER reject_olympus_research_evidence_mutation
    BEFORE UPDATE OR DELETE ON public.olympus_research_evidence
    FOR EACH ROW EXECUTE FUNCTION public.reject_olympus_research_state_mutation();
DROP TRIGGER IF EXISTS reject_olympus_research_evidence_truncate
    ON public.olympus_research_evidence;
CREATE TRIGGER reject_olympus_research_evidence_truncate
    BEFORE TRUNCATE ON public.olympus_research_evidence
    FOR EACH STATEMENT EXECUTE FUNCTION public.reject_olympus_research_state_mutation();

DROP TRIGGER IF EXISTS reject_olympus_research_belief_versions_mutation
    ON public.olympus_research_belief_versions;
CREATE TRIGGER reject_olympus_research_belief_versions_mutation
    BEFORE UPDATE OR DELETE ON public.olympus_research_belief_versions
    FOR EACH ROW EXECUTE FUNCTION public.reject_olympus_research_state_mutation();
DROP TRIGGER IF EXISTS reject_olympus_research_belief_versions_truncate
    ON public.olympus_research_belief_versions;
CREATE TRIGGER reject_olympus_research_belief_versions_truncate
    BEFORE TRUNCATE ON public.olympus_research_belief_versions
    FOR EACH STATEMENT EXECUTE FUNCTION public.reject_olympus_research_state_mutation();

DROP TRIGGER IF EXISTS reject_olympus_research_expected_event_versions_mutation
    ON public.olympus_research_expected_event_versions;
CREATE TRIGGER reject_olympus_research_expected_event_versions_mutation
    BEFORE UPDATE OR DELETE ON public.olympus_research_expected_event_versions
    FOR EACH ROW EXECUTE FUNCTION public.reject_olympus_research_state_mutation();
DROP TRIGGER IF EXISTS reject_olympus_research_expected_event_versions_truncate
    ON public.olympus_research_expected_event_versions;
CREATE TRIGGER reject_olympus_research_expected_event_versions_truncate
    BEFORE TRUNCATE ON public.olympus_research_expected_event_versions
    FOR EACH STATEMENT EXECUTE FUNCTION public.reject_olympus_research_state_mutation();

DROP TRIGGER IF EXISTS reject_olympus_research_patches_mutation
    ON public.olympus_research_patches;
CREATE TRIGGER reject_olympus_research_patches_mutation
    BEFORE UPDATE OR DELETE ON public.olympus_research_patches
    FOR EACH ROW EXECUTE FUNCTION public.reject_olympus_research_state_mutation();
DROP TRIGGER IF EXISTS reject_olympus_research_patches_truncate
    ON public.olympus_research_patches;
CREATE TRIGGER reject_olympus_research_patches_truncate
    BEFORE TRUNCATE ON public.olympus_research_patches
    FOR EACH STATEMENT EXECUTE FUNCTION public.reject_olympus_research_state_mutation();

DROP TRIGGER IF EXISTS reject_olympus_research_legacy_refs_mutation
    ON public.olympus_research_legacy_refs;
CREATE TRIGGER reject_olympus_research_legacy_refs_mutation
    BEFORE UPDATE OR DELETE ON public.olympus_research_legacy_refs
    FOR EACH ROW EXECUTE FUNCTION public.reject_olympus_research_state_mutation();
DROP TRIGGER IF EXISTS reject_olympus_research_legacy_refs_truncate
    ON public.olympus_research_legacy_refs;
CREATE TRIGGER reject_olympus_research_legacy_refs_truncate
    BEFORE TRUNCATE ON public.olympus_research_legacy_refs
    FOR EACH STATEMENT EXECUTE FUNCTION public.reject_olympus_research_state_mutation();

DROP TRIGGER IF EXISTS reject_olympus_research_state_versions_mutation
    ON public.olympus_research_state_versions;
CREATE TRIGGER reject_olympus_research_state_versions_mutation
    BEFORE UPDATE OR DELETE ON public.olympus_research_state_versions
    FOR EACH ROW EXECUTE FUNCTION public.reject_olympus_research_state_mutation();
DROP TRIGGER IF EXISTS reject_olympus_research_state_versions_truncate
    ON public.olympus_research_state_versions;
CREATE TRIGGER reject_olympus_research_state_versions_truncate
    BEFORE TRUNCATE ON public.olympus_research_state_versions
    FOR EACH STATEMENT EXECUTE FUNCTION public.reject_olympus_research_state_mutation();

DROP TRIGGER IF EXISTS reject_olympus_research_state_pins_mutation
    ON public.olympus_research_state_pins;
CREATE TRIGGER reject_olympus_research_state_pins_mutation
    BEFORE UPDATE OR DELETE ON public.olympus_research_state_pins
    FOR EACH ROW EXECUTE FUNCTION public.reject_olympus_research_state_mutation();
DROP TRIGGER IF EXISTS reject_olympus_research_state_pins_truncate
    ON public.olympus_research_state_pins;
CREATE TRIGGER reject_olympus_research_state_pins_truncate
    BEFORE TRUNCATE ON public.olympus_research_state_pins
    FOR EACH STATEMENT EXECUTE FUNCTION public.reject_olympus_research_state_mutation();

REVOKE ALL ON FUNCTION public.reject_olympus_research_state_mutation()
    FROM PUBLIC, anon, authenticated;

COMMENT ON TABLE public.olympus_research_evidence IS
    'Private append-only EvidenceRecord rows (#2854 / WP12.2). '
    'Exact content-hash identity; never UPDATE.';
COMMENT ON TABLE public.olympus_research_belief_versions IS
    'Private append-only BeliefVersion rows (#2854 / WP12.2). '
    'Supersession appends a child version; never rewrites parent.';
COMMENT ON TABLE public.olympus_research_expected_event_versions IS
    'Private append-only ExpectedEventVersion rows (#2854 / WP12.2).';
COMMENT ON TABLE public.olympus_research_patches IS
    'Private append-only ResearchPatch rows (#2854 / WP12.2).';
COMMENT ON TABLE public.olympus_research_legacy_refs IS
    'Legacy prose inventory only (#2854 / WP12.2). known_at IS NULL; '
    'strict readers exclude these rows.';
COMMENT ON TABLE public.olympus_research_state_versions IS
    'Private append-only ResearchStateVersion snapshots (#2854 / WP12.2). '
    'Content-addressed; optional parent lineage.';
COMMENT ON TABLE public.olympus_research_state_pins IS
    'Exact run/attempt ResearchStatePin (#2854 / WP12.2). '
    'One pin per (run_id, attempt_id); no load_latest after pin.';
COMMENT ON FUNCTION public.reject_olympus_research_state_mutation() IS
    'Rejects UPDATE, DELETE, and TRUNCATE on research-state tables (#2854).';
