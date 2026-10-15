-- 094_olympus_policy_replay.sql
--
-- Phase 4 WP16.2 private append-only policy replay governance store (#2983).
--
-- Persists WP16.1 replay manifests/pairs, append-only run events, immutable arm
-- results, comparison reports, gate criteria versions, evaluations, and human
-- governance decisions. Lifecycle is event-sourced — no mutable running-status row.
--
-- Dark launch: no public base view, no historical backfill, no worker wiring
-- (WP16.3+). Application store:
-- digiquant.olympus.replay.store.PolicyReplayStore.
--
-- Privacy: RLS enabled with zero policies; PUBLIC/anon/authenticated fully
-- revoked; service_role reset then SELECT+INSERT only. Append-only triggers
-- reject UPDATE/DELETE/TRUNCATE for every role.

CREATE TABLE IF NOT EXISTS public.olympus_replay_input_manifests (
    record_id uuid PRIMARY KEY,
    manifest_id text NOT NULL CHECK (length(manifest_id) BETWEEN 1 AND 500),
    manifest_content_hash text NOT NULL CHECK (length(manifest_content_hash) = 64),
    replay_as_of timestamptz NOT NULL,
    recorded_at timestamptz NOT NULL,
    schema_version integer NOT NULL CHECK (schema_version >= 1),
    payload jsonb NOT NULL CHECK (jsonb_typeof(payload) = 'object'),
    CONSTRAINT uq_olympus_replay_input_manifests_content_hash
        UNIQUE (manifest_content_hash)
);

CREATE TABLE IF NOT EXISTS public.olympus_replay_pairs (
    record_id uuid PRIMARY KEY,
    pair_id text NOT NULL CHECK (length(pair_id) BETWEEN 1 AND 500),
    pair_content_hash text NOT NULL CHECK (length(pair_content_hash) = 64),
    shared_manifest_content_hash text NOT NULL CHECK (length(shared_manifest_content_hash) = 64),
    recorded_at timestamptz NOT NULL,
    schema_version integer NOT NULL CHECK (schema_version >= 1),
    payload jsonb NOT NULL CHECK (jsonb_typeof(payload) = 'object'),
    CONSTRAINT uq_olympus_replay_pairs_content_hash
        UNIQUE (pair_content_hash),
    CONSTRAINT fk_olympus_replay_pairs_manifest_hash
        FOREIGN KEY (shared_manifest_content_hash)
        REFERENCES public.olympus_replay_input_manifests (manifest_content_hash)
);

CREATE TABLE IF NOT EXISTS public.olympus_replay_run_events (
    event_id uuid PRIMARY KEY,
    run_id text NOT NULL CHECK (length(run_id) BETWEEN 1 AND 500),
    pair_id text NOT NULL CHECK (length(pair_id) BETWEEN 1 AND 500),
    event_kind text NOT NULL CHECK (length(event_kind) BETWEEN 1 AND 64),
    sequence integer NOT NULL CHECK (sequence >= 0),
    recorded_at timestamptz NOT NULL,
    payload jsonb NOT NULL CHECK (jsonb_typeof(payload) = 'object'),
    CONSTRAINT uq_olympus_replay_run_events_run_sequence
        UNIQUE (run_id, sequence)
);

CREATE TABLE IF NOT EXISTS public.olympus_replay_arm_results (
    record_id uuid PRIMARY KEY,
    run_id text NOT NULL CHECK (length(run_id) BETWEEN 1 AND 500),
    arm_id text NOT NULL CHECK (length(arm_id) BETWEEN 1 AND 500),
    request_content_hash text NOT NULL CHECK (length(request_content_hash) = 64),
    result_content_hash text CHECK (result_content_hash IS NULL OR length(result_content_hash) = 64),
    recorded_at timestamptz NOT NULL,
    schema_version integer NOT NULL CHECK (schema_version >= 1),
    payload jsonb NOT NULL CHECK (jsonb_typeof(payload) = 'object'),
    CONSTRAINT uq_olympus_replay_arm_results_run_arm
        UNIQUE (run_id, arm_id)
);

CREATE TABLE IF NOT EXISTS public.olympus_policy_comparison_reports (
    comparison_id uuid PRIMARY KEY,
    pair_content_hash text NOT NULL CHECK (length(pair_content_hash) = 64),
    shared_manifest_content_hash text NOT NULL CHECK (length(shared_manifest_content_hash) = 64),
    report_content_hash text NOT NULL CHECK (length(report_content_hash) = 64),
    recorded_at timestamptz NOT NULL,
    schema_version integer NOT NULL CHECK (schema_version >= 1),
    payload jsonb NOT NULL CHECK (jsonb_typeof(payload) = 'object'),
    CONSTRAINT uq_olympus_policy_comparison_reports_content_hash
        UNIQUE (report_content_hash),
    CONSTRAINT fk_olympus_policy_comparison_reports_pair_hash
        FOREIGN KEY (pair_content_hash)
        REFERENCES public.olympus_replay_pairs (pair_content_hash),
    CONSTRAINT fk_olympus_policy_comparison_reports_manifest_hash
        FOREIGN KEY (shared_manifest_content_hash)
        REFERENCES public.olympus_replay_input_manifests (manifest_content_hash)
);

CREATE TABLE IF NOT EXISTS public.olympus_gate_criteria_versions (
    criteria_version_id uuid PRIMARY KEY,
    criteria_key text NOT NULL CHECK (length(criteria_key) BETWEEN 1 AND 500),
    content_hash text NOT NULL CHECK (length(content_hash) = 64),
    effective_at timestamptz NOT NULL,
    recorded_at timestamptz NOT NULL,
    supersedes_version_id uuid,
    schema_version integer NOT NULL CHECK (schema_version >= 1),
    payload jsonb NOT NULL CHECK (jsonb_typeof(payload) = 'object'),
    CONSTRAINT fk_olympus_gate_criteria_versions_supersedes
        FOREIGN KEY (supersedes_version_id)
        REFERENCES public.olympus_gate_criteria_versions (criteria_version_id),
    CONSTRAINT chk_olympus_gate_criteria_versions_no_self_supersede
        CHECK (
            supersedes_version_id IS NULL
            OR supersedes_version_id <> criteria_version_id
        )
);

CREATE TABLE IF NOT EXISTS public.olympus_gate_evaluations (
    evaluation_id uuid PRIMARY KEY,
    comparison_id uuid NOT NULL,
    criteria_version_id uuid NOT NULL,
    evaluation_content_hash text NOT NULL CHECK (length(evaluation_content_hash) = 64),
    recorded_at timestamptz NOT NULL,
    schema_version integer NOT NULL CHECK (schema_version >= 1),
    payload jsonb NOT NULL CHECK (jsonb_typeof(payload) = 'object'),
    CONSTRAINT uq_olympus_gate_evaluations_content_hash
        UNIQUE (evaluation_content_hash),
    CONSTRAINT fk_olympus_gate_evaluations_comparison
        FOREIGN KEY (comparison_id)
        REFERENCES public.olympus_policy_comparison_reports (comparison_id),
    CONSTRAINT fk_olympus_gate_evaluations_criteria
        FOREIGN KEY (criteria_version_id)
        REFERENCES public.olympus_gate_criteria_versions (criteria_version_id)
);

CREATE TABLE IF NOT EXISTS public.olympus_policy_governance_decisions (
    decision_id uuid PRIMARY KEY,
    evaluation_id uuid NOT NULL,
    decision_content_hash text NOT NULL CHECK (length(decision_content_hash) = 64),
    recorded_at timestamptz NOT NULL,
    supersedes_decision_id uuid,
    schema_version integer NOT NULL CHECK (schema_version >= 1),
    payload jsonb NOT NULL CHECK (jsonb_typeof(payload) = 'object'),
    CONSTRAINT fk_olympus_policy_governance_decisions_evaluation
        FOREIGN KEY (evaluation_id)
        REFERENCES public.olympus_gate_evaluations (evaluation_id),
    CONSTRAINT fk_olympus_policy_governance_decisions_supersedes
        FOREIGN KEY (supersedes_decision_id)
        REFERENCES public.olympus_policy_governance_decisions (decision_id),
    CONSTRAINT chk_olympus_policy_governance_decisions_no_self_supersede
        CHECK (
            supersedes_decision_id IS NULL
            OR supersedes_decision_id <> decision_id
        )
);

CREATE INDEX IF NOT EXISTS idx_olympus_replay_input_manifests_as_of
    ON public.olympus_replay_input_manifests (manifest_id, replay_as_of, recorded_at);

CREATE INDEX IF NOT EXISTS idx_olympus_replay_run_events_run
    ON public.olympus_replay_run_events (run_id, sequence);

CREATE INDEX IF NOT EXISTS idx_olympus_gate_criteria_versions_as_of
    ON public.olympus_gate_criteria_versions (criteria_key, effective_at, recorded_at);

CREATE INDEX IF NOT EXISTS idx_olympus_gate_evaluations_comparison
    ON public.olympus_gate_evaluations (comparison_id);

CREATE INDEX IF NOT EXISTS idx_olympus_policy_governance_decisions_evaluation
    ON public.olympus_policy_governance_decisions (evaluation_id);

ALTER TABLE public.olympus_replay_input_manifests ENABLE ROW LEVEL SECURITY;
ALTER TABLE public.olympus_replay_pairs ENABLE ROW LEVEL SECURITY;
ALTER TABLE public.olympus_replay_run_events ENABLE ROW LEVEL SECURITY;
ALTER TABLE public.olympus_replay_arm_results ENABLE ROW LEVEL SECURITY;
ALTER TABLE public.olympus_policy_comparison_reports ENABLE ROW LEVEL SECURITY;
ALTER TABLE public.olympus_gate_criteria_versions ENABLE ROW LEVEL SECURITY;
ALTER TABLE public.olympus_gate_evaluations ENABLE ROW LEVEL SECURITY;
ALTER TABLE public.olympus_policy_governance_decisions ENABLE ROW LEVEL SECURITY;

REVOKE ALL ON public.olympus_replay_input_manifests FROM PUBLIC, anon, authenticated;
REVOKE ALL ON public.olympus_replay_pairs FROM PUBLIC, anon, authenticated;
REVOKE ALL ON public.olympus_replay_run_events FROM PUBLIC, anon, authenticated;
REVOKE ALL ON public.olympus_replay_arm_results FROM PUBLIC, anon, authenticated;
REVOKE ALL ON public.olympus_policy_comparison_reports FROM PUBLIC, anon, authenticated;
REVOKE ALL ON public.olympus_gate_criteria_versions FROM PUBLIC, anon, authenticated;
REVOKE ALL ON public.olympus_gate_evaluations FROM PUBLIC, anon, authenticated;
REVOKE ALL ON public.olympus_policy_governance_decisions FROM PUBLIC, anon, authenticated;

REVOKE ALL ON public.olympus_replay_input_manifests FROM service_role;
REVOKE ALL ON public.olympus_replay_pairs FROM service_role;
REVOKE ALL ON public.olympus_replay_run_events FROM service_role;
REVOKE ALL ON public.olympus_replay_arm_results FROM service_role;
REVOKE ALL ON public.olympus_policy_comparison_reports FROM service_role;
REVOKE ALL ON public.olympus_gate_criteria_versions FROM service_role;
REVOKE ALL ON public.olympus_gate_evaluations FROM service_role;
REVOKE ALL ON public.olympus_policy_governance_decisions FROM service_role;

GRANT SELECT, INSERT ON public.olympus_replay_input_manifests TO service_role;
GRANT SELECT, INSERT ON public.olympus_replay_pairs TO service_role;
GRANT SELECT, INSERT ON public.olympus_replay_run_events TO service_role;
GRANT SELECT, INSERT ON public.olympus_replay_arm_results TO service_role;
GRANT SELECT, INSERT ON public.olympus_policy_comparison_reports TO service_role;
GRANT SELECT, INSERT ON public.olympus_gate_criteria_versions TO service_role;
GRANT SELECT, INSERT ON public.olympus_gate_evaluations TO service_role;
GRANT SELECT, INSERT ON public.olympus_policy_governance_decisions TO service_role;

CREATE OR REPLACE FUNCTION public.reject_olympus_policy_replay_mutation()
RETURNS trigger
LANGUAGE plpgsql
SET search_path = ''
AS $$
BEGIN
    RAISE EXCEPTION 'policy replay governance store is append-only (#2983)'
        USING ERRCODE = '55000';
END
$$;

DROP TRIGGER IF EXISTS reject_olympus_replay_input_manifests_mutation
    ON public.olympus_replay_input_manifests;
CREATE TRIGGER reject_olympus_replay_input_manifests_mutation
    BEFORE UPDATE OR DELETE ON public.olympus_replay_input_manifests
    FOR EACH ROW EXECUTE FUNCTION public.reject_olympus_policy_replay_mutation();
DROP TRIGGER IF EXISTS reject_olympus_replay_input_manifests_truncate
    ON public.olympus_replay_input_manifests;
CREATE TRIGGER reject_olympus_replay_input_manifests_truncate
    BEFORE TRUNCATE ON public.olympus_replay_input_manifests
    FOR EACH STATEMENT EXECUTE FUNCTION public.reject_olympus_policy_replay_mutation();

DROP TRIGGER IF EXISTS reject_olympus_replay_pairs_mutation
    ON public.olympus_replay_pairs;
CREATE TRIGGER reject_olympus_replay_pairs_mutation
    BEFORE UPDATE OR DELETE ON public.olympus_replay_pairs
    FOR EACH ROW EXECUTE FUNCTION public.reject_olympus_policy_replay_mutation();
DROP TRIGGER IF EXISTS reject_olympus_replay_pairs_truncate
    ON public.olympus_replay_pairs;
CREATE TRIGGER reject_olympus_replay_pairs_truncate
    BEFORE TRUNCATE ON public.olympus_replay_pairs
    FOR EACH STATEMENT EXECUTE FUNCTION public.reject_olympus_policy_replay_mutation();

DROP TRIGGER IF EXISTS reject_olympus_replay_run_events_mutation
    ON public.olympus_replay_run_events;
CREATE TRIGGER reject_olympus_replay_run_events_mutation
    BEFORE UPDATE OR DELETE ON public.olympus_replay_run_events
    FOR EACH ROW EXECUTE FUNCTION public.reject_olympus_policy_replay_mutation();
DROP TRIGGER IF EXISTS reject_olympus_replay_run_events_truncate
    ON public.olympus_replay_run_events;
CREATE TRIGGER reject_olympus_replay_run_events_truncate
    BEFORE TRUNCATE ON public.olympus_replay_run_events
    FOR EACH STATEMENT EXECUTE FUNCTION public.reject_olympus_policy_replay_mutation();

DROP TRIGGER IF EXISTS reject_olympus_replay_arm_results_mutation
    ON public.olympus_replay_arm_results;
CREATE TRIGGER reject_olympus_replay_arm_results_mutation
    BEFORE UPDATE OR DELETE ON public.olympus_replay_arm_results
    FOR EACH ROW EXECUTE FUNCTION public.reject_olympus_policy_replay_mutation();
DROP TRIGGER IF EXISTS reject_olympus_replay_arm_results_truncate
    ON public.olympus_replay_arm_results;
CREATE TRIGGER reject_olympus_replay_arm_results_truncate
    BEFORE TRUNCATE ON public.olympus_replay_arm_results
    FOR EACH STATEMENT EXECUTE FUNCTION public.reject_olympus_policy_replay_mutation();

DROP TRIGGER IF EXISTS reject_olympus_policy_comparison_reports_mutation
    ON public.olympus_policy_comparison_reports;
CREATE TRIGGER reject_olympus_policy_comparison_reports_mutation
    BEFORE UPDATE OR DELETE ON public.olympus_policy_comparison_reports
    FOR EACH ROW EXECUTE FUNCTION public.reject_olympus_policy_replay_mutation();
DROP TRIGGER IF EXISTS reject_olympus_policy_comparison_reports_truncate
    ON public.olympus_policy_comparison_reports;
CREATE TRIGGER reject_olympus_policy_comparison_reports_truncate
    BEFORE TRUNCATE ON public.olympus_policy_comparison_reports
    FOR EACH STATEMENT EXECUTE FUNCTION public.reject_olympus_policy_replay_mutation();

DROP TRIGGER IF EXISTS reject_olympus_gate_criteria_versions_mutation
    ON public.olympus_gate_criteria_versions;
CREATE TRIGGER reject_olympus_gate_criteria_versions_mutation
    BEFORE UPDATE OR DELETE ON public.olympus_gate_criteria_versions
    FOR EACH ROW EXECUTE FUNCTION public.reject_olympus_policy_replay_mutation();
DROP TRIGGER IF EXISTS reject_olympus_gate_criteria_versions_truncate
    ON public.olympus_gate_criteria_versions;
CREATE TRIGGER reject_olympus_gate_criteria_versions_truncate
    BEFORE TRUNCATE ON public.olympus_gate_criteria_versions
    FOR EACH STATEMENT EXECUTE FUNCTION public.reject_olympus_policy_replay_mutation();

DROP TRIGGER IF EXISTS reject_olympus_gate_evaluations_mutation
    ON public.olympus_gate_evaluations;
CREATE TRIGGER reject_olympus_gate_evaluations_mutation
    BEFORE UPDATE OR DELETE ON public.olympus_gate_evaluations
    FOR EACH ROW EXECUTE FUNCTION public.reject_olympus_policy_replay_mutation();
DROP TRIGGER IF EXISTS reject_olympus_gate_evaluations_truncate
    ON public.olympus_gate_evaluations;
CREATE TRIGGER reject_olympus_gate_evaluations_truncate
    BEFORE TRUNCATE ON public.olympus_gate_evaluations
    FOR EACH STATEMENT EXECUTE FUNCTION public.reject_olympus_policy_replay_mutation();

DROP TRIGGER IF EXISTS reject_olympus_policy_governance_decisions_mutation
    ON public.olympus_policy_governance_decisions;
CREATE TRIGGER reject_olympus_policy_governance_decisions_mutation
    BEFORE UPDATE OR DELETE ON public.olympus_policy_governance_decisions
    FOR EACH ROW EXECUTE FUNCTION public.reject_olympus_policy_replay_mutation();
DROP TRIGGER IF EXISTS reject_olympus_policy_governance_decisions_truncate
    ON public.olympus_policy_governance_decisions;
CREATE TRIGGER reject_olympus_policy_governance_decisions_truncate
    BEFORE TRUNCATE ON public.olympus_policy_governance_decisions
    FOR EACH STATEMENT EXECUTE FUNCTION public.reject_olympus_policy_replay_mutation();

REVOKE ALL ON FUNCTION public.reject_olympus_policy_replay_mutation()
    FROM PUBLIC, anon, authenticated;

COMMENT ON TABLE public.olympus_replay_input_manifests IS
    'Private append-only ReplayInputManifest rows (#2983 / WP16.2). '
    'Content-addressed by manifest_content_hash; never UPDATE.';
COMMENT ON TABLE public.olympus_replay_pairs IS
    'Private append-only ReplayPairSpec rows (#2983 / WP16.2). '
    'Paired arms share one manifest_content_hash FK.';
COMMENT ON TABLE public.olympus_replay_run_events IS
    'Append-only replay run lifecycle events (#2983 / WP16.2). '
    'No mutable running-status row — derive status from events.';
COMMENT ON TABLE public.olympus_replay_arm_results IS
    'Immutable final PortfolioReplayResult per run/arm (#2983 / WP16.2).';
COMMENT ON TABLE public.olympus_policy_comparison_reports IS
    'Immutable PolicyComparisonReport envelopes (#2983 / WP16.2).';
COMMENT ON TABLE public.olympus_gate_criteria_versions IS
    'Immutable human-authored gate criteria versions (#2983 / WP16.2).';
COMMENT ON TABLE public.olympus_gate_evaluations IS
    'Immutable gate evaluation results (#2983 / WP16.2).';
COMMENT ON TABLE public.olympus_policy_governance_decisions IS
    'Immutable authenticated human governance decisions (#2983 / WP16.2). '
    'Records accountability only — never activates production policy.';
COMMENT ON FUNCTION public.reject_olympus_policy_replay_mutation() IS
    'Rejects UPDATE, DELETE, and TRUNCATE on policy replay governance tables (#2983).';
