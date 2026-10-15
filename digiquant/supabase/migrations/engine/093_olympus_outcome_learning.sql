-- 093_olympus_outcome_learning.sql
--
-- Phase 4 WP15.2 private append-only outcome-learning store (#2959).
--
-- Persists frozen WP15.1 contracts (OutcomeEpisode, ComponentAttributionReport,
-- OutcomeLessonVersion) as exact-version structured learning memory. Distinct
-- from legacy beliefs_distillation prose and atlas decision_log reflection.
--
-- Dark launch: no public base view, no historical backfill, no assembler wiring
-- (WP15.3+). Application store:
-- digiquant.olympus.learning.outcome_store.OutcomeLearningStore.
--
-- Privacy: RLS enabled with zero policies; PUBLIC/anon/authenticated fully
-- revoked; service_role reset then SELECT+INSERT only. Append-only triggers
-- reject UPDATE/DELETE/TRUNCATE for every role.
--
-- Unwrapped on purpose: db-migrate.yml applies the file and its ledger row in
-- one psql single-transaction call. DDL is replay-safe through IF NOT EXISTS,
-- CREATE OR REPLACE, and DROP TRIGGER IF EXISTS before CREATE TRIGGER.

CREATE TABLE IF NOT EXISTS public.olympus_outcome_episodes (
    episode_version_id uuid PRIMARY KEY,
    episode_key text NOT NULL CHECK (length(episode_key) BETWEEN 1 AND 500),
    content_hash text NOT NULL CHECK (length(content_hash) = 64),
    supersedes_version_id uuid,
    effective_at timestamptz NOT NULL,
    known_at timestamptz NOT NULL,
    recorded_at timestamptz NOT NULL,
    horizon_end timestamptz NOT NULL,
    available_at timestamptz NOT NULL,
    schema_version integer NOT NULL CHECK (schema_version >= 1),
    payload jsonb NOT NULL CHECK (jsonb_typeof(payload) = 'object'),
    CONSTRAINT fk_olympus_outcome_episodes_supersedes
        FOREIGN KEY (supersedes_version_id)
        REFERENCES public.olympus_outcome_episodes (episode_version_id),
    CONSTRAINT chk_olympus_outcome_episodes_no_self_supersede
        CHECK (
            supersedes_version_id IS NULL
            OR supersedes_version_id <> episode_version_id
        ),
    CONSTRAINT chk_olympus_outcome_episodes_available_gte_horizon
        CHECK (available_at >= horizon_end),
    CONSTRAINT chk_olympus_outcome_episodes_known_lte_available
        CHECK (known_at <= available_at)
);

CREATE TABLE IF NOT EXISTS public.olympus_component_attribution_reports (
    report_id uuid PRIMARY KEY,
    episode_version_id uuid NOT NULL,
    schema_version integer NOT NULL CHECK (schema_version >= 1),
    payload jsonb NOT NULL CHECK (jsonb_typeof(payload) = 'object'),
    CONSTRAINT fk_olympus_component_attribution_reports_episode
        FOREIGN KEY (episode_version_id)
        REFERENCES public.olympus_outcome_episodes (episode_version_id)
);

CREATE TABLE IF NOT EXISTS public.olympus_outcome_lesson_versions (
    lesson_version_id uuid PRIMARY KEY,
    compilation_policy_id text NOT NULL CHECK (length(compilation_policy_id) BETWEEN 1 AND 500),
    content_hash text NOT NULL CHECK (length(content_hash) = 64),
    supersedes_version_id uuid,
    compilation_cutoff timestamptz NOT NULL,
    available_at timestamptz NOT NULL,
    cohort text NOT NULL CHECK (length(cohort) BETWEEN 1 AND 500),
    horizon_id text NOT NULL CHECK (length(horizon_id) BETWEEN 1 AND 500),
    component text NOT NULL CHECK (length(component) BETWEEN 1 AND 64),
    schema_version integer NOT NULL CHECK (schema_version >= 1),
    payload jsonb NOT NULL CHECK (jsonb_typeof(payload) = 'object'),
    CONSTRAINT fk_olympus_outcome_lesson_versions_supersedes
        FOREIGN KEY (supersedes_version_id)
        REFERENCES public.olympus_outcome_lesson_versions (lesson_version_id),
    CONSTRAINT chk_olympus_outcome_lesson_versions_no_self_supersede
        CHECK (
            supersedes_version_id IS NULL
            OR supersedes_version_id <> lesson_version_id
        ),
    CONSTRAINT chk_olympus_outcome_lesson_versions_available_gte_cutoff
        CHECK (available_at >= compilation_cutoff)
);

CREATE INDEX IF NOT EXISTS idx_olympus_outcome_episodes_as_of
    ON public.olympus_outcome_episodes (episode_key, available_at, known_at);

CREATE INDEX IF NOT EXISTS idx_olympus_outcome_episodes_supersedes
    ON public.olympus_outcome_episodes (supersedes_version_id);

CREATE INDEX IF NOT EXISTS idx_olympus_component_attribution_reports_episode
    ON public.olympus_component_attribution_reports (episode_version_id);

CREATE INDEX IF NOT EXISTS idx_olympus_outcome_lesson_versions_as_of
    ON public.olympus_outcome_lesson_versions (
        compilation_policy_id,
        cohort,
        component,
        horizon_id,
        available_at
    );

ALTER TABLE public.olympus_outcome_episodes ENABLE ROW LEVEL SECURITY;
ALTER TABLE public.olympus_component_attribution_reports ENABLE ROW LEVEL SECURITY;
ALTER TABLE public.olympus_outcome_lesson_versions ENABLE ROW LEVEL SECURITY;

REVOKE ALL ON public.olympus_outcome_episodes FROM PUBLIC, anon, authenticated;
REVOKE ALL ON public.olympus_component_attribution_reports FROM PUBLIC, anon, authenticated;
REVOKE ALL ON public.olympus_outcome_lesson_versions FROM PUBLIC, anon, authenticated;

REVOKE ALL ON public.olympus_outcome_episodes FROM service_role;
REVOKE ALL ON public.olympus_component_attribution_reports FROM service_role;
REVOKE ALL ON public.olympus_outcome_lesson_versions FROM service_role;

GRANT SELECT, INSERT ON public.olympus_outcome_episodes TO service_role;
GRANT SELECT, INSERT ON public.olympus_component_attribution_reports TO service_role;
GRANT SELECT, INSERT ON public.olympus_outcome_lesson_versions TO service_role;

CREATE OR REPLACE FUNCTION public.reject_olympus_outcome_learning_mutation()
RETURNS trigger
LANGUAGE plpgsql
SET search_path = ''
AS $$
BEGIN
    RAISE EXCEPTION 'outcome learning store is append-only (#2959)'
        USING ERRCODE = '55000';
END
$$;

DROP TRIGGER IF EXISTS reject_olympus_outcome_episodes_mutation
    ON public.olympus_outcome_episodes;
CREATE TRIGGER reject_olympus_outcome_episodes_mutation
    BEFORE UPDATE OR DELETE ON public.olympus_outcome_episodes
    FOR EACH ROW EXECUTE FUNCTION public.reject_olympus_outcome_learning_mutation();
DROP TRIGGER IF EXISTS reject_olympus_outcome_episodes_truncate
    ON public.olympus_outcome_episodes;
CREATE TRIGGER reject_olympus_outcome_episodes_truncate
    BEFORE TRUNCATE ON public.olympus_outcome_episodes
    FOR EACH STATEMENT EXECUTE FUNCTION public.reject_olympus_outcome_learning_mutation();

DROP TRIGGER IF EXISTS reject_olympus_component_attribution_reports_mutation
    ON public.olympus_component_attribution_reports;
CREATE TRIGGER reject_olympus_component_attribution_reports_mutation
    BEFORE UPDATE OR DELETE ON public.olympus_component_attribution_reports
    FOR EACH ROW EXECUTE FUNCTION public.reject_olympus_outcome_learning_mutation();
DROP TRIGGER IF EXISTS reject_olympus_component_attribution_reports_truncate
    ON public.olympus_component_attribution_reports;
CREATE TRIGGER reject_olympus_component_attribution_reports_truncate
    BEFORE TRUNCATE ON public.olympus_component_attribution_reports
    FOR EACH STATEMENT EXECUTE FUNCTION public.reject_olympus_outcome_learning_mutation();

DROP TRIGGER IF EXISTS reject_olympus_outcome_lesson_versions_mutation
    ON public.olympus_outcome_lesson_versions;
CREATE TRIGGER reject_olympus_outcome_lesson_versions_mutation
    BEFORE UPDATE OR DELETE ON public.olympus_outcome_lesson_versions
    FOR EACH ROW EXECUTE FUNCTION public.reject_olympus_outcome_learning_mutation();
DROP TRIGGER IF EXISTS reject_olympus_outcome_lesson_versions_truncate
    ON public.olympus_outcome_lesson_versions;
CREATE TRIGGER reject_olympus_outcome_lesson_versions_truncate
    BEFORE TRUNCATE ON public.olympus_outcome_lesson_versions
    FOR EACH STATEMENT EXECUTE FUNCTION public.reject_olympus_outcome_learning_mutation();

REVOKE ALL ON FUNCTION public.reject_olympus_outcome_learning_mutation()
    FROM PUBLIC, anon, authenticated;

COMMENT ON TABLE public.olympus_outcome_episodes IS
    'Private append-only OutcomeEpisode rows (#2959 / WP15.2). '
    'Content-addressed; supersession appends a child version; never UPDATE.';
COMMENT ON TABLE public.olympus_component_attribution_reports IS
    'Private append-only ComponentAttributionReport rows (#2959 / WP15.2). '
    'FK → episode version; honest component observations only.';
COMMENT ON TABLE public.olympus_outcome_lesson_versions IS
    'Private append-only OutcomeLessonVersion rows (#2959 / WP15.2). '
    'Structured lesson membership via payload episode/report IDs.';
COMMENT ON FUNCTION public.reject_olympus_outcome_learning_mutation() IS
    'Rejects UPDATE, DELETE, and TRUNCATE on outcome-learning tables (#2959).';
