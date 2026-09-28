-- 134_rename_phase_b_olympus_objects.sql
-- Phase B of the `olympus_*` terminology removal (#4295 gap G5).
--
-- Phase A (132) added new-name compatibility views over the still-old-named
-- base objects. This migration completes the switch on the database side:
--
--   1. drop the Phase-A new-name views;
--   2. rename the 47 base tables `olympus_<x>` -> `<x>`;
--   3. rename the 3 pre-existing `olympus_*` views to their stripped names;
--   4. recreate each old name as a compatibility view over the new object;
--   5. rename the 15 `reject_olympus_*()` trigger functions;
--   6. rename 64 standalone indexes, 97 named constraints and 93 triggers.
--
-- ORDERING. The Phase-A views are dropped first so the base-table names are
-- free for the renames. The recreated old-name views are built afterwards,
-- from the already-renamed objects, so their bodies reference the new names.
-- Triggers reference their functions by OID, so renaming a function cannot
-- break a trigger; the trigger renames are therefore cosmetic (error text and
-- catalog hygiene only).
--
-- `security_invoker = true` is MANDATORY on every recreated old-name base
-- view. The PostgreSQL default (false) runs the view as its owner and bypasses
-- the base table's RLS policies -- the `atlas_run_health` unauthenticated-DELETE
-- defect documented at digiquant/supabase/README.md. `olympus_run_event_trace`
-- deliberately keeps its original `security_invoker = false` (066/086); the two
-- position_events projections keep `security_invoker = true` (071).
--
-- COLLISION. `olympus_position_events` becomes `position_events_labeled`, never
-- `position_events` (a base table since migration 001).
--
-- GRANTS. Service role gets SELECT + INSERT on the base-table compatibility
-- views; authenticated additionally gets SELECT on the four accounting/profile
-- tables. Anon + authenticated keep SELECT on `run_event_trace`; the two
-- position_events projections lost anon in 129 and keep authenticated + service
-- role. No old-name view is ever granted UPDATE, DELETE or TRUNCATE.
--
-- HARD EXCLUSION. `olympus_schema_migrations` is the db-migrate ledger and is
-- NOT touched here. db-migrate.yml creates it IF NOT EXISTS and gates on it;
-- renaming it would re-create the OLD name empty on the next run -- the
-- documented forged-ledger catastrophe. It has its own future, human-gated
-- change.
--
-- Replay-safe: unwrapped (db-migrate.yml runs this file plus its ledger INSERT
-- inside one `psql --single-transaction`). Never add a bare BEGIN/COMMIT here.

-- ---------------------------------------------------------------------------
-- 1. Drop the Phase-A new-name compatibility views (migration 132).
-- ---------------------------------------------------------------------------
DROP VIEW IF EXISTS public.accounting_contributions;
DROP VIEW IF EXISTS public.accounting_holdings;
DROP VIEW IF EXISTS public.accounting_periods;
DROP VIEW IF EXISTS public.action_cost_estimates;
DROP VIEW IF EXISTS public.action_cost_outcomes;
DROP VIEW IF EXISTS public.attention_context_manifests;
DROP VIEW IF EXISTS public.attention_decision_attempts;
DROP VIEW IF EXISTS public.attention_decisions;
DROP VIEW IF EXISTS public.attention_plans;
DROP VIEW IF EXISTS public.attention_policy_evaluations;
DROP VIEW IF EXISTS public.calibrated_forecasts;
DROP VIEW IF EXISTS public.component_attribution_reports;
DROP VIEW IF EXISTS public.covariance_snapshots;
DROP VIEW IF EXISTS public.evidence_bundle_amendments;
DROP VIEW IF EXISTS public.forecast_amendments;
DROP VIEW IF EXISTS public.forecast_assessments;
DROP VIEW IF EXISTS public.forecast_calibrations;
DROP VIEW IF EXISTS public.forecast_outcomes;
DROP VIEW IF EXISTS public.gate_criteria_versions;
DROP VIEW IF EXISTS public.gate_evaluations;
DROP VIEW IF EXISTS public.h8_risk_run_refs;
DROP VIEW IF EXISTS public.liquidity_snapshots;
DROP VIEW IF EXISTS public.missing_fact_requests;
DROP VIEW IF EXISTS public.node_runs;
DROP VIEW IF EXISTS public.outcome_episodes;
DROP VIEW IF EXISTS public.outcome_lesson_versions;
DROP VIEW IF EXISTS public.policy_comparison_reports;
DROP VIEW IF EXISTS public.policy_governance_decisions;
DROP VIEW IF EXISTS public.pretrade_risk_reports;
DROP VIEW IF EXISTS public.profile_config;
DROP VIEW IF EXISTS public.provider_attempts;
DROP VIEW IF EXISTS public.provider_calls;
DROP VIEW IF EXISTS public.replay_arm_results;
DROP VIEW IF EXISTS public.replay_input_manifests;
DROP VIEW IF EXISTS public.replay_pairs;
DROP VIEW IF EXISTS public.replay_run_events;
DROP VIEW IF EXISTS public.research_belief_versions;
DROP VIEW IF EXISTS public.research_corpus;
DROP VIEW IF EXISTS public.research_evidence;
DROP VIEW IF EXISTS public.research_expected_event_versions;
DROP VIEW IF EXISTS public.research_legacy_refs;
DROP VIEW IF EXISTS public.research_patches;
DROP VIEW IF EXISTS public.research_state_pins;
DROP VIEW IF EXISTS public.research_state_versions;
DROP VIEW IF EXISTS public.risk_policies;
DROP VIEW IF EXISTS public.run_events;
DROP VIEW IF EXISTS public.ticker_evidence_bundles;
DROP VIEW IF EXISTS public.run_event_trace;
DROP VIEW IF EXISTS public.position_events_labeled;
DROP VIEW IF EXISTS public.position_events_authoritative;

-- ---------------------------------------------------------------------------
-- 2. Rename the 47 base tables olympus_<x> -> <x>.
-- ---------------------------------------------------------------------------
ALTER TABLE public.olympus_accounting_contributions RENAME TO accounting_contributions;
ALTER TABLE public.olympus_accounting_holdings RENAME TO accounting_holdings;
ALTER TABLE public.olympus_accounting_periods RENAME TO accounting_periods;
ALTER TABLE public.olympus_action_cost_estimates RENAME TO action_cost_estimates;
ALTER TABLE public.olympus_action_cost_outcomes RENAME TO action_cost_outcomes;
ALTER TABLE public.olympus_attention_context_manifests RENAME TO attention_context_manifests;
ALTER TABLE public.olympus_attention_decision_attempts RENAME TO attention_decision_attempts;
ALTER TABLE public.olympus_attention_decisions RENAME TO attention_decisions;
ALTER TABLE public.olympus_attention_plans RENAME TO attention_plans;
ALTER TABLE public.olympus_attention_policy_evaluations RENAME TO attention_policy_evaluations;
ALTER TABLE public.olympus_calibrated_forecasts RENAME TO calibrated_forecasts;
ALTER TABLE public.olympus_component_attribution_reports RENAME TO component_attribution_reports;
ALTER TABLE public.olympus_covariance_snapshots RENAME TO covariance_snapshots;
ALTER TABLE public.olympus_evidence_bundle_amendments RENAME TO evidence_bundle_amendments;
ALTER TABLE public.olympus_forecast_amendments RENAME TO forecast_amendments;
ALTER TABLE public.olympus_forecast_assessments RENAME TO forecast_assessments;
ALTER TABLE public.olympus_forecast_calibrations RENAME TO forecast_calibrations;
ALTER TABLE public.olympus_forecast_outcomes RENAME TO forecast_outcomes;
ALTER TABLE public.olympus_gate_criteria_versions RENAME TO gate_criteria_versions;
ALTER TABLE public.olympus_gate_evaluations RENAME TO gate_evaluations;
ALTER TABLE public.olympus_h8_risk_run_refs RENAME TO h8_risk_run_refs;
ALTER TABLE public.olympus_liquidity_snapshots RENAME TO liquidity_snapshots;
ALTER TABLE public.olympus_missing_fact_requests RENAME TO missing_fact_requests;
ALTER TABLE public.olympus_node_runs RENAME TO node_runs;
ALTER TABLE public.olympus_outcome_episodes RENAME TO outcome_episodes;
ALTER TABLE public.olympus_outcome_lesson_versions RENAME TO outcome_lesson_versions;
ALTER TABLE public.olympus_policy_comparison_reports RENAME TO policy_comparison_reports;
ALTER TABLE public.olympus_policy_governance_decisions RENAME TO policy_governance_decisions;
ALTER TABLE public.olympus_pretrade_risk_reports RENAME TO pretrade_risk_reports;
ALTER TABLE public.olympus_profile_config RENAME TO profile_config;
ALTER TABLE public.olympus_provider_attempts RENAME TO provider_attempts;
ALTER TABLE public.olympus_provider_calls RENAME TO provider_calls;
ALTER TABLE public.olympus_replay_arm_results RENAME TO replay_arm_results;
ALTER TABLE public.olympus_replay_input_manifests RENAME TO replay_input_manifests;
ALTER TABLE public.olympus_replay_pairs RENAME TO replay_pairs;
ALTER TABLE public.olympus_replay_run_events RENAME TO replay_run_events;
ALTER TABLE public.olympus_research_belief_versions RENAME TO research_belief_versions;
ALTER TABLE public.olympus_research_corpus RENAME TO research_corpus;
ALTER TABLE public.olympus_research_evidence RENAME TO research_evidence;
ALTER TABLE public.olympus_research_expected_event_versions RENAME TO research_expected_event_versions;
ALTER TABLE public.olympus_research_legacy_refs RENAME TO research_legacy_refs;
ALTER TABLE public.olympus_research_patches RENAME TO research_patches;
ALTER TABLE public.olympus_research_state_pins RENAME TO research_state_pins;
ALTER TABLE public.olympus_research_state_versions RENAME TO research_state_versions;
ALTER TABLE public.olympus_risk_policies RENAME TO risk_policies;
ALTER TABLE public.olympus_run_events RENAME TO run_events;
ALTER TABLE public.olympus_ticker_evidence_bundles RENAME TO ticker_evidence_bundles;

-- ---------------------------------------------------------------------------
-- 3. Rename the 3 pre-existing olympus_* views.
-- ---------------------------------------------------------------------------
ALTER VIEW public.olympus_run_event_trace RENAME TO run_event_trace;
ALTER VIEW public.olympus_position_events RENAME TO position_events_labeled;
ALTER VIEW public.olympus_position_events_authoritative RENAME TO position_events_authoritative;

-- ---------------------------------------------------------------------------
-- 4. Recreate the 47 old-name base-table views (auto-updatable,
--    security_invoker = true). The old names are free after section 2.
-- ---------------------------------------------------------------------------
CREATE VIEW public.olympus_accounting_contributions WITH (security_invoker = true) AS
SELECT * FROM public.accounting_contributions;
REVOKE ALL ON public.olympus_accounting_contributions FROM PUBLIC, anon, authenticated, service_role;
GRANT SELECT, INSERT ON public.olympus_accounting_contributions TO service_role;
GRANT SELECT ON public.olympus_accounting_contributions TO authenticated;

CREATE VIEW public.olympus_accounting_holdings WITH (security_invoker = true) AS
SELECT * FROM public.accounting_holdings;
REVOKE ALL ON public.olympus_accounting_holdings FROM PUBLIC, anon, authenticated, service_role;
GRANT SELECT, INSERT ON public.olympus_accounting_holdings TO service_role;
GRANT SELECT ON public.olympus_accounting_holdings TO authenticated;

CREATE VIEW public.olympus_accounting_periods WITH (security_invoker = true) AS
SELECT * FROM public.accounting_periods;
REVOKE ALL ON public.olympus_accounting_periods FROM PUBLIC, anon, authenticated, service_role;
GRANT SELECT, INSERT ON public.olympus_accounting_periods TO service_role;
GRANT SELECT ON public.olympus_accounting_periods TO authenticated;

CREATE VIEW public.olympus_action_cost_estimates WITH (security_invoker = true) AS
SELECT * FROM public.action_cost_estimates;
REVOKE ALL ON public.olympus_action_cost_estimates FROM PUBLIC, anon, authenticated, service_role;
GRANT SELECT, INSERT ON public.olympus_action_cost_estimates TO service_role;

CREATE VIEW public.olympus_action_cost_outcomes WITH (security_invoker = true) AS
SELECT * FROM public.action_cost_outcomes;
REVOKE ALL ON public.olympus_action_cost_outcomes FROM PUBLIC, anon, authenticated, service_role;
GRANT SELECT, INSERT ON public.olympus_action_cost_outcomes TO service_role;

CREATE VIEW public.olympus_attention_context_manifests WITH (security_invoker = true) AS
SELECT * FROM public.attention_context_manifests;
REVOKE ALL ON public.olympus_attention_context_manifests FROM PUBLIC, anon, authenticated, service_role;
GRANT SELECT, INSERT ON public.olympus_attention_context_manifests TO service_role;

CREATE VIEW public.olympus_attention_decision_attempts WITH (security_invoker = true) AS
SELECT * FROM public.attention_decision_attempts;
REVOKE ALL ON public.olympus_attention_decision_attempts FROM PUBLIC, anon, authenticated, service_role;
GRANT SELECT, INSERT ON public.olympus_attention_decision_attempts TO service_role;

CREATE VIEW public.olympus_attention_decisions WITH (security_invoker = true) AS
SELECT * FROM public.attention_decisions;
REVOKE ALL ON public.olympus_attention_decisions FROM PUBLIC, anon, authenticated, service_role;
GRANT SELECT, INSERT ON public.olympus_attention_decisions TO service_role;

CREATE VIEW public.olympus_attention_plans WITH (security_invoker = true) AS
SELECT * FROM public.attention_plans;
REVOKE ALL ON public.olympus_attention_plans FROM PUBLIC, anon, authenticated, service_role;
GRANT SELECT, INSERT ON public.olympus_attention_plans TO service_role;

CREATE VIEW public.olympus_attention_policy_evaluations WITH (security_invoker = true) AS
SELECT * FROM public.attention_policy_evaluations;
REVOKE ALL ON public.olympus_attention_policy_evaluations FROM PUBLIC, anon, authenticated, service_role;
GRANT SELECT, INSERT ON public.olympus_attention_policy_evaluations TO service_role;

CREATE VIEW public.olympus_calibrated_forecasts WITH (security_invoker = true) AS
SELECT * FROM public.calibrated_forecasts;
REVOKE ALL ON public.olympus_calibrated_forecasts FROM PUBLIC, anon, authenticated, service_role;
GRANT SELECT, INSERT ON public.olympus_calibrated_forecasts TO service_role;

CREATE VIEW public.olympus_component_attribution_reports WITH (security_invoker = true) AS
SELECT * FROM public.component_attribution_reports;
REVOKE ALL ON public.olympus_component_attribution_reports FROM PUBLIC, anon, authenticated, service_role;
GRANT SELECT, INSERT ON public.olympus_component_attribution_reports TO service_role;

CREATE VIEW public.olympus_covariance_snapshots WITH (security_invoker = true) AS
SELECT * FROM public.covariance_snapshots;
REVOKE ALL ON public.olympus_covariance_snapshots FROM PUBLIC, anon, authenticated, service_role;
GRANT SELECT, INSERT ON public.olympus_covariance_snapshots TO service_role;

CREATE VIEW public.olympus_evidence_bundle_amendments WITH (security_invoker = true) AS
SELECT * FROM public.evidence_bundle_amendments;
REVOKE ALL ON public.olympus_evidence_bundle_amendments FROM PUBLIC, anon, authenticated, service_role;
GRANT SELECT, INSERT ON public.olympus_evidence_bundle_amendments TO service_role;

CREATE VIEW public.olympus_forecast_amendments WITH (security_invoker = true) AS
SELECT * FROM public.forecast_amendments;
REVOKE ALL ON public.olympus_forecast_amendments FROM PUBLIC, anon, authenticated, service_role;
GRANT SELECT, INSERT ON public.olympus_forecast_amendments TO service_role;

CREATE VIEW public.olympus_forecast_assessments WITH (security_invoker = true) AS
SELECT * FROM public.forecast_assessments;
REVOKE ALL ON public.olympus_forecast_assessments FROM PUBLIC, anon, authenticated, service_role;
GRANT SELECT, INSERT ON public.olympus_forecast_assessments TO service_role;

CREATE VIEW public.olympus_forecast_calibrations WITH (security_invoker = true) AS
SELECT * FROM public.forecast_calibrations;
REVOKE ALL ON public.olympus_forecast_calibrations FROM PUBLIC, anon, authenticated, service_role;
GRANT SELECT, INSERT ON public.olympus_forecast_calibrations TO service_role;

CREATE VIEW public.olympus_forecast_outcomes WITH (security_invoker = true) AS
SELECT * FROM public.forecast_outcomes;
REVOKE ALL ON public.olympus_forecast_outcomes FROM PUBLIC, anon, authenticated, service_role;
GRANT SELECT, INSERT ON public.olympus_forecast_outcomes TO service_role;

CREATE VIEW public.olympus_gate_criteria_versions WITH (security_invoker = true) AS
SELECT * FROM public.gate_criteria_versions;
REVOKE ALL ON public.olympus_gate_criteria_versions FROM PUBLIC, anon, authenticated, service_role;
GRANT SELECT, INSERT ON public.olympus_gate_criteria_versions TO service_role;

CREATE VIEW public.olympus_gate_evaluations WITH (security_invoker = true) AS
SELECT * FROM public.gate_evaluations;
REVOKE ALL ON public.olympus_gate_evaluations FROM PUBLIC, anon, authenticated, service_role;
GRANT SELECT, INSERT ON public.olympus_gate_evaluations TO service_role;

CREATE VIEW public.olympus_h8_risk_run_refs WITH (security_invoker = true) AS
SELECT * FROM public.h8_risk_run_refs;
REVOKE ALL ON public.olympus_h8_risk_run_refs FROM PUBLIC, anon, authenticated, service_role;
GRANT SELECT, INSERT ON public.olympus_h8_risk_run_refs TO service_role;

CREATE VIEW public.olympus_liquidity_snapshots WITH (security_invoker = true) AS
SELECT * FROM public.liquidity_snapshots;
REVOKE ALL ON public.olympus_liquidity_snapshots FROM PUBLIC, anon, authenticated, service_role;
GRANT SELECT, INSERT ON public.olympus_liquidity_snapshots TO service_role;

CREATE VIEW public.olympus_missing_fact_requests WITH (security_invoker = true) AS
SELECT * FROM public.missing_fact_requests;
REVOKE ALL ON public.olympus_missing_fact_requests FROM PUBLIC, anon, authenticated, service_role;
GRANT SELECT, INSERT ON public.olympus_missing_fact_requests TO service_role;

CREATE VIEW public.olympus_node_runs WITH (security_invoker = true) AS
SELECT * FROM public.node_runs;
REVOKE ALL ON public.olympus_node_runs FROM PUBLIC, anon, authenticated, service_role;
GRANT SELECT, INSERT ON public.olympus_node_runs TO service_role;

CREATE VIEW public.olympus_outcome_episodes WITH (security_invoker = true) AS
SELECT * FROM public.outcome_episodes;
REVOKE ALL ON public.olympus_outcome_episodes FROM PUBLIC, anon, authenticated, service_role;
GRANT SELECT, INSERT ON public.olympus_outcome_episodes TO service_role;

CREATE VIEW public.olympus_outcome_lesson_versions WITH (security_invoker = true) AS
SELECT * FROM public.outcome_lesson_versions;
REVOKE ALL ON public.olympus_outcome_lesson_versions FROM PUBLIC, anon, authenticated, service_role;
GRANT SELECT, INSERT ON public.olympus_outcome_lesson_versions TO service_role;

CREATE VIEW public.olympus_policy_comparison_reports WITH (security_invoker = true) AS
SELECT * FROM public.policy_comparison_reports;
REVOKE ALL ON public.olympus_policy_comparison_reports FROM PUBLIC, anon, authenticated, service_role;
GRANT SELECT, INSERT ON public.olympus_policy_comparison_reports TO service_role;

CREATE VIEW public.olympus_policy_governance_decisions WITH (security_invoker = true) AS
SELECT * FROM public.policy_governance_decisions;
REVOKE ALL ON public.olympus_policy_governance_decisions FROM PUBLIC, anon, authenticated, service_role;
GRANT SELECT, INSERT ON public.olympus_policy_governance_decisions TO service_role;

CREATE VIEW public.olympus_pretrade_risk_reports WITH (security_invoker = true) AS
SELECT * FROM public.pretrade_risk_reports;
REVOKE ALL ON public.olympus_pretrade_risk_reports FROM PUBLIC, anon, authenticated, service_role;
GRANT SELECT, INSERT ON public.olympus_pretrade_risk_reports TO service_role;

CREATE VIEW public.olympus_profile_config WITH (security_invoker = true) AS
SELECT * FROM public.profile_config;
REVOKE ALL ON public.olympus_profile_config FROM PUBLIC, anon, authenticated, service_role;
GRANT SELECT, INSERT ON public.olympus_profile_config TO service_role;
GRANT SELECT ON public.olympus_profile_config TO authenticated;

CREATE VIEW public.olympus_provider_attempts WITH (security_invoker = true) AS
SELECT * FROM public.provider_attempts;
REVOKE ALL ON public.olympus_provider_attempts FROM PUBLIC, anon, authenticated, service_role;
GRANT SELECT, INSERT ON public.olympus_provider_attempts TO service_role;

CREATE VIEW public.olympus_provider_calls WITH (security_invoker = true) AS
SELECT * FROM public.provider_calls;
REVOKE ALL ON public.olympus_provider_calls FROM PUBLIC, anon, authenticated, service_role;
GRANT SELECT, INSERT ON public.olympus_provider_calls TO service_role;

CREATE VIEW public.olympus_replay_arm_results WITH (security_invoker = true) AS
SELECT * FROM public.replay_arm_results;
REVOKE ALL ON public.olympus_replay_arm_results FROM PUBLIC, anon, authenticated, service_role;
GRANT SELECT, INSERT ON public.olympus_replay_arm_results TO service_role;

CREATE VIEW public.olympus_replay_input_manifests WITH (security_invoker = true) AS
SELECT * FROM public.replay_input_manifests;
REVOKE ALL ON public.olympus_replay_input_manifests FROM PUBLIC, anon, authenticated, service_role;
GRANT SELECT, INSERT ON public.olympus_replay_input_manifests TO service_role;

CREATE VIEW public.olympus_replay_pairs WITH (security_invoker = true) AS
SELECT * FROM public.replay_pairs;
REVOKE ALL ON public.olympus_replay_pairs FROM PUBLIC, anon, authenticated, service_role;
GRANT SELECT, INSERT ON public.olympus_replay_pairs TO service_role;

CREATE VIEW public.olympus_replay_run_events WITH (security_invoker = true) AS
SELECT * FROM public.replay_run_events;
REVOKE ALL ON public.olympus_replay_run_events FROM PUBLIC, anon, authenticated, service_role;
GRANT SELECT, INSERT ON public.olympus_replay_run_events TO service_role;

CREATE VIEW public.olympus_research_belief_versions WITH (security_invoker = true) AS
SELECT * FROM public.research_belief_versions;
REVOKE ALL ON public.olympus_research_belief_versions FROM PUBLIC, anon, authenticated, service_role;
GRANT SELECT, INSERT ON public.olympus_research_belief_versions TO service_role;

CREATE VIEW public.olympus_research_corpus WITH (security_invoker = true) AS
SELECT * FROM public.research_corpus;
REVOKE ALL ON public.olympus_research_corpus FROM PUBLIC, anon, authenticated, service_role;
GRANT SELECT, INSERT ON public.olympus_research_corpus TO service_role;

CREATE VIEW public.olympus_research_evidence WITH (security_invoker = true) AS
SELECT * FROM public.research_evidence;
REVOKE ALL ON public.olympus_research_evidence FROM PUBLIC, anon, authenticated, service_role;
GRANT SELECT, INSERT ON public.olympus_research_evidence TO service_role;

CREATE VIEW public.olympus_research_expected_event_versions WITH (security_invoker = true) AS
SELECT * FROM public.research_expected_event_versions;
REVOKE ALL ON public.olympus_research_expected_event_versions FROM PUBLIC, anon, authenticated, service_role;
GRANT SELECT, INSERT ON public.olympus_research_expected_event_versions TO service_role;

CREATE VIEW public.olympus_research_legacy_refs WITH (security_invoker = true) AS
SELECT * FROM public.research_legacy_refs;
REVOKE ALL ON public.olympus_research_legacy_refs FROM PUBLIC, anon, authenticated, service_role;
GRANT SELECT, INSERT ON public.olympus_research_legacy_refs TO service_role;

CREATE VIEW public.olympus_research_patches WITH (security_invoker = true) AS
SELECT * FROM public.research_patches;
REVOKE ALL ON public.olympus_research_patches FROM PUBLIC, anon, authenticated, service_role;
GRANT SELECT, INSERT ON public.olympus_research_patches TO service_role;

CREATE VIEW public.olympus_research_state_pins WITH (security_invoker = true) AS
SELECT * FROM public.research_state_pins;
REVOKE ALL ON public.olympus_research_state_pins FROM PUBLIC, anon, authenticated, service_role;
GRANT SELECT, INSERT ON public.olympus_research_state_pins TO service_role;

CREATE VIEW public.olympus_research_state_versions WITH (security_invoker = true) AS
SELECT * FROM public.research_state_versions;
REVOKE ALL ON public.olympus_research_state_versions FROM PUBLIC, anon, authenticated, service_role;
GRANT SELECT, INSERT ON public.olympus_research_state_versions TO service_role;

CREATE VIEW public.olympus_risk_policies WITH (security_invoker = true) AS
SELECT * FROM public.risk_policies;
REVOKE ALL ON public.olympus_risk_policies FROM PUBLIC, anon, authenticated, service_role;
GRANT SELECT, INSERT ON public.olympus_risk_policies TO service_role;

CREATE VIEW public.olympus_run_events WITH (security_invoker = true) AS
SELECT * FROM public.run_events;
REVOKE ALL ON public.olympus_run_events FROM PUBLIC, anon, authenticated, service_role;
GRANT SELECT, INSERT ON public.olympus_run_events TO service_role;

CREATE VIEW public.olympus_ticker_evidence_bundles WITH (security_invoker = true) AS
SELECT * FROM public.ticker_evidence_bundles;
REVOKE ALL ON public.olympus_ticker_evidence_bundles FROM PUBLIC, anon, authenticated, service_role;
GRANT SELECT, INSERT ON public.olympus_ticker_evidence_bundles TO service_role;


-- ---------------------------------------------------------------------------
-- 5. Recreate the 3 old-name views with their original definitions and
--    original security_invoker settings.
-- ---------------------------------------------------------------------------
-- olympus_run_event_trace: definer view (security_invoker = false), the
-- curated Pipeline call trace from 066, restated with WP1 join keys in 086.
CREATE VIEW public.olympus_run_event_trace WITH (security_invoker = false) AS
SELECT
    run_id,
    attempt,
    run_date,
    run_type,
    sequence,
    event_kind,
    phase,
    operation,
    document_key,
    name,
    status,
    duration_ms,
    retry_count,
    sources,
    input_summary,
    output_summary,
    created_at,
    call_id,
    attempt_id,
    node_run_id
FROM public.run_events;
REVOKE ALL ON public.olympus_run_event_trace FROM PUBLIC, anon, authenticated, service_role;
GRANT SELECT ON public.olympus_run_event_trace TO anon, authenticated, service_role;

-- olympus_position_events: labeled compatibility projection of the
-- `position_events` base table (migration 071).
CREATE VIEW public.olympus_position_events WITH (security_invoker = true) AS
SELECT
    id,
    date,
    ticker,
    event,
    weight_pct,
    prev_weight_pct,
    cumulative_return_since_event_pct,
    price,
    thesis_id,
    reason,
    created_at,
    book_source
FROM public.position_events;
REVOKE ALL ON public.olympus_position_events FROM PUBLIC, anon, authenticated, service_role;
GRANT SELECT ON public.olympus_position_events TO authenticated, service_role;

-- olympus_position_events_authoritative: authoritative-only projection (071).
CREATE VIEW public.olympus_position_events_authoritative WITH (security_invoker = true) AS
SELECT
    id,
    date,
    ticker,
    event,
    weight_pct,
    prev_weight_pct,
    cumulative_return_since_event_pct,
    price,
    thesis_id,
    reason,
    created_at,
    book_source
FROM public.position_events
WHERE book_source = 'authoritative';
REVOKE ALL ON public.olympus_position_events_authoritative FROM PUBLIC, anon, authenticated, service_role;
GRANT SELECT ON public.olympus_position_events_authoritative TO authenticated, service_role;

-- ---------------------------------------------------------------------------
-- 6. Rename the 15 `reject_olympus_*()` trigger functions.
--    Triggers hold the function OID, so they keep firing after the rename.
-- ---------------------------------------------------------------------------
ALTER FUNCTION public.reject_olympus_accounting_mutation() RENAME TO reject_accounting_mutation;
ALTER FUNCTION public.reject_olympus_attention_context_mutation() RENAME TO reject_attention_context_mutation;
ALTER FUNCTION public.reject_olympus_cost_liquidity_mutation() RENAME TO reject_cost_liquidity_mutation;
ALTER FUNCTION public.reject_olympus_evidence_amendment_base_mismatch() RENAME TO reject_evidence_amendment_base_mismatch;
ALTER FUNCTION public.reject_olympus_evidence_bundle_mutation() RENAME TO reject_evidence_bundle_mutation;
ALTER FUNCTION public.reject_olympus_forecast_calibration_mutation() RENAME TO reject_forecast_calibration_mutation;
ALTER FUNCTION public.reject_olympus_forecast_registry_mutation() RENAME TO reject_forecast_registry_mutation;
ALTER FUNCTION public.reject_olympus_outcome_learning_mutation() RENAME TO reject_outcome_learning_mutation;
ALTER FUNCTION public.reject_olympus_policy_replay_mutation() RENAME TO reject_policy_replay_mutation;
ALTER FUNCTION public.reject_olympus_pretrade_risk_report_mutation() RENAME TO reject_pretrade_risk_report_mutation;
ALTER FUNCTION public.reject_olympus_profile_config_mutation() RENAME TO reject_profile_config_mutation;
ALTER FUNCTION public.reject_olympus_provider_telemetry_mutation() RENAME TO reject_provider_telemetry_mutation;
ALTER FUNCTION public.reject_olympus_research_corpus_mutation() RENAME TO reject_research_corpus_mutation;
ALTER FUNCTION public.reject_olympus_research_state_mutation() RENAME TO reject_research_state_mutation;
ALTER FUNCTION public.reject_olympus_risk_policy_snapshot_mutation() RENAME TO reject_risk_policy_snapshot_mutation;

-- ---------------------------------------------------------------------------
-- 7. Rename the 64 standalone indexes (PK/UNIQUE constraints
--    carry their backing index via section 8; these are CREATE INDEX ones).
-- ---------------------------------------------------------------------------
ALTER INDEX public.idx_olympus_accounting_contributions_period RENAME TO idx_accounting_contributions_period;
ALTER INDEX public.idx_olympus_accounting_contributions_workspace RENAME TO idx_accounting_contributions_workspace;
ALTER INDEX public.idx_olympus_accounting_holdings_period RENAME TO idx_accounting_holdings_period;
ALTER INDEX public.idx_olympus_accounting_holdings_workspace RENAME TO idx_accounting_holdings_workspace;
ALTER INDEX public.idx_olympus_accounting_periods_status_date RENAME TO idx_accounting_periods_status_date;
ALTER INDEX public.idx_olympus_accounting_periods_workspace RENAME TO idx_accounting_periods_workspace;
ALTER INDEX public.idx_olympus_action_cost_estimates_effective RENAME TO idx_action_cost_estimates_effective;
ALTER INDEX public.idx_olympus_action_cost_estimates_order RENAME TO idx_action_cost_estimates_order;
ALTER INDEX public.idx_olympus_action_cost_outcomes_estimate RENAME TO idx_action_cost_outcomes_estimate;
ALTER INDEX public.idx_olympus_attention_context_manifests_plan RENAME TO idx_attention_context_manifests_plan;
ALTER INDEX public.idx_olympus_attention_decisions_plan RENAME TO idx_attention_decisions_plan;
ALTER INDEX public.idx_olympus_attention_decisions_recorded RENAME TO idx_attention_decisions_recorded;
ALTER INDEX public.idx_olympus_attention_plans_recorded RENAME TO idx_attention_plans_recorded;
ALTER INDEX public.idx_olympus_attention_policy_evaluations_plan RENAME TO idx_attention_policy_evaluations_plan;
ALTER INDEX public.idx_olympus_calibrated_forecasts_effective_known RENAME TO idx_calibrated_forecasts_effective_known;
ALTER INDEX public.idx_olympus_component_attribution_reports_episode RENAME TO idx_component_attribution_reports_episode;
ALTER INDEX public.idx_olympus_covariance_snapshots_session RENAME TO idx_covariance_snapshots_session;
ALTER INDEX public.idx_olympus_evidence_bundle_amendments_base RENAME TO idx_evidence_bundle_amendments_base;
ALTER INDEX public.idx_olympus_forecast_amendments_base_known RENAME TO idx_forecast_amendments_base_known;
ALTER INDEX public.idx_olympus_forecast_amendments_ticker_known RENAME TO idx_forecast_amendments_ticker_known;
ALTER INDEX public.idx_olympus_forecast_assessments_run RENAME TO idx_forecast_assessments_run;
ALTER INDEX public.idx_olympus_forecast_assessments_ticker_known RENAME TO idx_forecast_assessments_ticker_known;
ALTER INDEX public.idx_olympus_forecast_calibrations_cohort_known RENAME TO idx_forecast_calibrations_cohort_known;
ALTER INDEX public.idx_olympus_forecast_outcomes_effective_maturity RENAME TO idx_forecast_outcomes_effective_maturity;
ALTER INDEX public.idx_olympus_forecast_outcomes_ticker_known RENAME TO idx_forecast_outcomes_ticker_known;
ALTER INDEX public.idx_olympus_gate_criteria_versions_as_of RENAME TO idx_gate_criteria_versions_as_of;
ALTER INDEX public.idx_olympus_gate_evaluations_comparison RENAME TO idx_gate_evaluations_comparison;
ALTER INDEX public.idx_olympus_h8_risk_run_refs_run_date RENAME TO idx_h8_risk_run_refs_run_date;
ALTER INDEX public.idx_olympus_liquidity_snapshots_order RENAME TO idx_liquidity_snapshots_order;
ALTER INDEX public.idx_olympus_missing_fact_requests_base RENAME TO idx_missing_fact_requests_base;
ALTER INDEX public.idx_olympus_node_runs_run_id RENAME TO idx_node_runs_run_id;
ALTER INDEX public.idx_olympus_outcome_episodes_as_of RENAME TO idx_outcome_episodes_as_of;
ALTER INDEX public.idx_olympus_outcome_episodes_supersedes RENAME TO idx_outcome_episodes_supersedes;
ALTER INDEX public.idx_olympus_outcome_lesson_versions_as_of RENAME TO idx_outcome_lesson_versions_as_of;
ALTER INDEX public.idx_olympus_policy_governance_decisions_evaluation RENAME TO idx_policy_governance_decisions_evaluation;
ALTER INDEX public.idx_olympus_pretrade_risk_reports_book_fp RENAME TO idx_pretrade_risk_reports_book_fp;
ALTER INDEX public.idx_olympus_pretrade_risk_reports_run RENAME TO idx_pretrade_risk_reports_run;
ALTER INDEX public.idx_olympus_pretrade_risk_reports_session RENAME TO idx_pretrade_risk_reports_session;
ALTER INDEX public.idx_olympus_profile_config_key_recorded RENAME TO idx_profile_config_key_recorded;
ALTER INDEX public.idx_olympus_profile_config_workspace RENAME TO idx_profile_config_workspace;
ALTER INDEX public.idx_olympus_provider_calls_node_run_id RENAME TO idx_provider_calls_node_run_id;
ALTER INDEX public.idx_olympus_replay_input_manifests_as_of RENAME TO idx_replay_input_manifests_as_of;
ALTER INDEX public.idx_olympus_replay_run_events_run RENAME TO idx_replay_run_events_run;
ALTER INDEX public.idx_olympus_research_belief_versions_known RENAME TO idx_research_belief_versions_known;
ALTER INDEX public.idx_olympus_research_corpus_kind_recorded RENAME TO idx_research_corpus_kind_recorded;
ALTER INDEX public.idx_olympus_research_evidence_known RENAME TO idx_research_evidence_known;
ALTER INDEX public.idx_olympus_research_expected_event_versions_known RENAME TO idx_research_expected_event_versions_known;
ALTER INDEX public.idx_olympus_research_patches_known RENAME TO idx_research_patches_known;
ALTER INDEX public.idx_olympus_research_state_pins_version RENAME TO idx_research_state_pins_version;
ALTER INDEX public.idx_olympus_research_state_versions_as_of RENAME TO idx_research_state_versions_as_of;
ALTER INDEX public.idx_olympus_research_state_versions_parent RENAME TO idx_research_state_versions_parent;
ALTER INDEX public.idx_olympus_risk_policies_effective RENAME TO idx_risk_policies_effective;
ALTER INDEX public.idx_olympus_ticker_evidence_bundles_known RENAME TO idx_ticker_evidence_bundles_known;
ALTER INDEX public.idx_olympus_ticker_evidence_bundles_state RENAME TO idx_ticker_evidence_bundles_state;
ALTER INDEX public.olympus_run_events_attempt_id_idx RENAME TO run_events_attempt_id_idx;
ALTER INDEX public.olympus_run_events_call_id_idx RENAME TO run_events_call_id_idx;
ALTER INDEX public.olympus_run_events_phase_idx RENAME TO run_events_phase_idx;
ALTER INDEX public.olympus_run_events_run_date_idx RENAME TO run_events_run_date_idx;
ALTER INDEX public.uq_olympus_accounting_periods_one_root RENAME TO uq_accounting_periods_one_root;
ALTER INDEX public.uq_olympus_accounting_periods_supersedes RENAME TO uq_accounting_periods_supersedes;
ALTER INDEX public.uq_olympus_forecast_outcomes_effective_maturity RENAME TO uq_forecast_outcomes_effective_maturity;
ALTER INDEX public.uq_olympus_profile_config_one_house_root RENAME TO uq_profile_config_one_house_root;
ALTER INDEX public.uq_olympus_profile_config_supersedes RENAME TO uq_profile_config_supersedes;
ALTER INDEX public.uq_olympus_research_corpus_key RENAME TO uq_research_corpus_key;

-- ---------------------------------------------------------------------------
-- 8. Rename the 97 named constraints. Renaming a PRIMARY KEY
--    or UNIQUE constraint also renames its backing index.
-- ---------------------------------------------------------------------------
ALTER TABLE public.accounting_periods RENAME CONSTRAINT chk_olympus_accounting_periods_final_clean TO chk_accounting_periods_final_clean;
ALTER TABLE public.accounting_periods RENAME CONSTRAINT chk_olympus_accounting_periods_no_self_supersede TO chk_accounting_periods_no_self_supersede;
ALTER TABLE public.forecast_amendments RENAME CONSTRAINT chk_olympus_forecast_amendments_no_self_supersede TO chk_forecast_amendments_no_self_supersede;
ALTER TABLE public.forecast_outcomes RENAME CONSTRAINT chk_olympus_forecast_outcomes_session_order TO chk_forecast_outcomes_session_order;
ALTER TABLE public.gate_criteria_versions RENAME CONSTRAINT chk_olympus_gate_criteria_versions_no_self_supersede TO chk_gate_criteria_versions_no_self_supersede;
ALTER TABLE public.node_runs RENAME CONSTRAINT chk_olympus_node_runs_lifecycle TO chk_node_runs_lifecycle;
ALTER TABLE public.node_runs RENAME CONSTRAINT chk_olympus_node_runs_time_order TO chk_node_runs_time_order;
ALTER TABLE public.outcome_episodes RENAME CONSTRAINT chk_olympus_outcome_episodes_available_gte_horizon TO chk_outcome_episodes_available_gte_horizon;
ALTER TABLE public.outcome_episodes RENAME CONSTRAINT chk_olympus_outcome_episodes_known_lte_available TO chk_outcome_episodes_known_lte_available;
ALTER TABLE public.outcome_episodes RENAME CONSTRAINT chk_olympus_outcome_episodes_no_self_supersede TO chk_outcome_episodes_no_self_supersede;
ALTER TABLE public.outcome_lesson_versions RENAME CONSTRAINT chk_olympus_outcome_lesson_versions_available_gte_cutoff TO chk_outcome_lesson_versions_available_gte_cutoff;
ALTER TABLE public.outcome_lesson_versions RENAME CONSTRAINT chk_olympus_outcome_lesson_versions_no_self_supersede TO chk_outcome_lesson_versions_no_self_supersede;
ALTER TABLE public.policy_governance_decisions RENAME CONSTRAINT chk_olympus_policy_governance_decisions_no_self_supersede TO chk_policy_governance_decisions_no_self_supersede;
ALTER TABLE public.profile_config RENAME CONSTRAINT chk_olympus_profile_config_house_key TO chk_profile_config_house_key;
ALTER TABLE public.provider_attempts RENAME CONSTRAINT chk_olympus_provider_attempts_lifecycle TO chk_provider_attempts_lifecycle;
ALTER TABLE public.provider_attempts RENAME CONSTRAINT chk_olympus_provider_attempts_retry TO chk_provider_attempts_retry;
ALTER TABLE public.provider_attempts RENAME CONSTRAINT chk_olympus_provider_attempts_time_order TO chk_provider_attempts_time_order;
ALTER TABLE public.provider_calls RENAME CONSTRAINT chk_olympus_provider_calls_artifact_disposition TO chk_provider_calls_artifact_disposition;
ALTER TABLE public.provider_calls RENAME CONSTRAINT chk_olympus_provider_calls_attempts TO chk_provider_calls_attempts;
ALTER TABLE public.provider_calls RENAME CONSTRAINT chk_olympus_provider_calls_error_type TO chk_provider_calls_error_type;
ALTER TABLE public.provider_calls RENAME CONSTRAINT chk_olympus_provider_calls_lifecycle TO chk_provider_calls_lifecycle;
ALTER TABLE public.provider_calls RENAME CONSTRAINT chk_olympus_provider_calls_terminal_disposition TO chk_provider_calls_terminal_disposition;
ALTER TABLE public.provider_calls RENAME CONSTRAINT chk_olympus_provider_calls_time_order TO chk_provider_calls_time_order;
ALTER TABLE public.research_belief_versions RENAME CONSTRAINT chk_olympus_research_belief_versions_no_self_supersede TO chk_research_belief_versions_no_self_supersede;
ALTER TABLE public.research_corpus RENAME CONSTRAINT chk_olympus_research_corpus_no_tenant_payload TO chk_research_corpus_no_tenant_payload;
ALTER TABLE public.research_evidence RENAME CONSTRAINT chk_olympus_research_evidence_no_self_supersede TO chk_research_evidence_no_self_supersede;
ALTER TABLE public.research_expected_event_versions RENAME CONSTRAINT chk_olympus_research_expected_event_versions_no_self_supersede TO chk_research_expected_event_versions_no_self_supersede;
ALTER TABLE public.research_legacy_refs RENAME CONSTRAINT chk_olympus_research_legacy_refs_null_known TO chk_research_legacy_refs_null_known;
ALTER TABLE public.research_patches RENAME CONSTRAINT chk_olympus_research_patches_no_self_supersede TO chk_research_patches_no_self_supersede;
ALTER TABLE public.research_state_pins RENAME CONSTRAINT chk_olympus_research_state_pins_temporal TO chk_research_state_pins_temporal;
ALTER TABLE public.research_state_versions RENAME CONSTRAINT chk_olympus_research_state_versions_no_self_parent TO chk_research_state_versions_no_self_parent;
ALTER TABLE public.accounting_contributions RENAME CONSTRAINT fk_olympus_accounting_contributions_period TO fk_accounting_contributions_period;
ALTER TABLE public.accounting_contributions RENAME CONSTRAINT fk_olympus_accounting_contributions_workspace TO fk_accounting_contributions_workspace;
ALTER TABLE public.accounting_holdings RENAME CONSTRAINT fk_olympus_accounting_holdings_period TO fk_accounting_holdings_period;
ALTER TABLE public.accounting_holdings RENAME CONSTRAINT fk_olympus_accounting_holdings_workspace TO fk_accounting_holdings_workspace;
ALTER TABLE public.accounting_periods RENAME CONSTRAINT fk_olympus_accounting_periods_supersedes TO fk_accounting_periods_supersedes;
ALTER TABLE public.accounting_periods RENAME CONSTRAINT fk_olympus_accounting_periods_workspace TO fk_accounting_periods_workspace;
ALTER TABLE public.action_cost_estimates RENAME CONSTRAINT fk_olympus_action_cost_estimates_snapshot TO fk_action_cost_estimates_snapshot;
ALTER TABLE public.action_cost_outcomes RENAME CONSTRAINT fk_olympus_action_cost_outcomes_estimate TO fk_action_cost_outcomes_estimate;
ALTER TABLE public.attention_context_manifests RENAME CONSTRAINT fk_olympus_attention_context_manifests_decision TO fk_attention_context_manifests_decision;
ALTER TABLE public.attention_context_manifests RENAME CONSTRAINT fk_olympus_attention_context_manifests_plan TO fk_attention_context_manifests_plan;
ALTER TABLE public.attention_decision_attempts RENAME CONSTRAINT fk_olympus_attention_decision_attempts_decision TO fk_attention_decision_attempts_decision;
ALTER TABLE public.attention_decision_attempts RENAME CONSTRAINT fk_olympus_attention_decision_attempts_provider TO fk_attention_decision_attempts_provider;
ALTER TABLE public.attention_decisions RENAME CONSTRAINT fk_olympus_attention_decisions_plan TO fk_attention_decisions_plan;
ALTER TABLE public.attention_policy_evaluations RENAME CONSTRAINT fk_olympus_attention_policy_evaluations_plan TO fk_attention_policy_evaluations_plan;
ALTER TABLE public.calibrated_forecasts RENAME CONSTRAINT fk_olympus_calibrated_forecasts_base TO fk_calibrated_forecasts_base;
ALTER TABLE public.calibrated_forecasts RENAME CONSTRAINT fk_olympus_calibrated_forecasts_calibration TO fk_calibrated_forecasts_calibration;
ALTER TABLE public.component_attribution_reports RENAME CONSTRAINT fk_olympus_component_attribution_reports_episode TO fk_component_attribution_reports_episode;
ALTER TABLE public.evidence_bundle_amendments RENAME CONSTRAINT fk_olympus_evidence_bundle_amendments_base TO fk_evidence_bundle_amendments_base;
ALTER TABLE public.evidence_bundle_amendments RENAME CONSTRAINT fk_olympus_evidence_bundle_amendments_request TO fk_evidence_bundle_amendments_request;
ALTER TABLE public.forecast_amendments RENAME CONSTRAINT fk_olympus_forecast_amendments_base TO fk_forecast_amendments_base;
ALTER TABLE public.forecast_amendments RENAME CONSTRAINT fk_olympus_forecast_amendments_supersedes TO fk_forecast_amendments_supersedes;
ALTER TABLE public.forecast_outcomes RENAME CONSTRAINT fk_olympus_forecast_outcomes_base TO fk_forecast_outcomes_base;
ALTER TABLE public.gate_criteria_versions RENAME CONSTRAINT fk_olympus_gate_criteria_versions_supersedes TO fk_gate_criteria_versions_supersedes;
ALTER TABLE public.gate_evaluations RENAME CONSTRAINT fk_olympus_gate_evaluations_comparison TO fk_gate_evaluations_comparison;
ALTER TABLE public.gate_evaluations RENAME CONSTRAINT fk_olympus_gate_evaluations_criteria TO fk_gate_evaluations_criteria;
ALTER TABLE public.h8_risk_run_refs RENAME CONSTRAINT fk_olympus_h8_risk_run_refs_policy TO fk_h8_risk_run_refs_policy;
ALTER TABLE public.h8_risk_run_refs RENAME CONSTRAINT fk_olympus_h8_risk_run_refs_snapshot TO fk_h8_risk_run_refs_snapshot;
ALTER TABLE public.missing_fact_requests RENAME CONSTRAINT fk_olympus_missing_fact_requests_base TO fk_missing_fact_requests_base;
ALTER TABLE public.outcome_episodes RENAME CONSTRAINT fk_olympus_outcome_episodes_supersedes TO fk_outcome_episodes_supersedes;
ALTER TABLE public.outcome_lesson_versions RENAME CONSTRAINT fk_olympus_outcome_lesson_versions_supersedes TO fk_outcome_lesson_versions_supersedes;
ALTER TABLE public.policy_comparison_reports RENAME CONSTRAINT fk_olympus_policy_comparison_reports_manifest_hash TO fk_policy_comparison_reports_manifest_hash;
ALTER TABLE public.policy_comparison_reports RENAME CONSTRAINT fk_olympus_policy_comparison_reports_pair_hash TO fk_policy_comparison_reports_pair_hash;
ALTER TABLE public.policy_governance_decisions RENAME CONSTRAINT fk_olympus_policy_governance_decisions_evaluation TO fk_policy_governance_decisions_evaluation;
ALTER TABLE public.policy_governance_decisions RENAME CONSTRAINT fk_olympus_policy_governance_decisions_supersedes TO fk_policy_governance_decisions_supersedes;
ALTER TABLE public.profile_config RENAME CONSTRAINT fk_olympus_profile_config_workspace TO fk_profile_config_workspace;
ALTER TABLE public.provider_attempts RENAME CONSTRAINT fk_olympus_provider_attempts_call TO fk_provider_attempts_call;
ALTER TABLE public.provider_calls RENAME CONSTRAINT fk_olympus_provider_calls_node_run TO fk_provider_calls_node_run;
ALTER TABLE public.provider_calls RENAME CONSTRAINT fk_olympus_provider_calls_parent TO fk_provider_calls_parent;
ALTER TABLE public.replay_pairs RENAME CONSTRAINT fk_olympus_replay_pairs_manifest_hash TO fk_replay_pairs_manifest_hash;
ALTER TABLE public.research_belief_versions RENAME CONSTRAINT fk_olympus_research_belief_versions_supersedes TO fk_research_belief_versions_supersedes;
ALTER TABLE public.research_evidence RENAME CONSTRAINT fk_olympus_research_evidence_supersedes TO fk_research_evidence_supersedes;
ALTER TABLE public.research_expected_event_versions RENAME CONSTRAINT fk_olympus_research_expected_event_versions_supersedes TO fk_research_expected_event_versions_supersedes;
ALTER TABLE public.research_patches RENAME CONSTRAINT fk_olympus_research_patches_supersedes TO fk_research_patches_supersedes;
ALTER TABLE public.research_state_pins RENAME CONSTRAINT fk_olympus_research_state_pins_version TO fk_research_state_pins_version;
ALTER TABLE public.research_state_versions RENAME CONSTRAINT fk_olympus_research_state_versions_parent TO fk_research_state_versions_parent;
ALTER TABLE public.provider_calls RENAME CONSTRAINT olympus_provider_calls_purpose_check TO provider_calls_purpose_check;
ALTER TABLE public.run_events RENAME CONSTRAINT olympus_run_events_cached_tokens_check TO run_events_cached_tokens_check;
ALTER TABLE public.run_events RENAME CONSTRAINT olympus_run_events_completion_tokens_check TO run_events_completion_tokens_check;
ALTER TABLE public.run_events RENAME CONSTRAINT olympus_run_events_cost_usd_check TO run_events_cost_usd_check;
ALTER TABLE public.run_events RENAME CONSTRAINT olympus_run_events_prompt_tokens_check TO run_events_prompt_tokens_check;
ALTER TABLE public.attention_decision_attempts RENAME CONSTRAINT pk_olympus_attention_decision_attempts TO pk_attention_decision_attempts;
ALTER TABLE public.accounting_contributions RENAME CONSTRAINT uq_olympus_accounting_contributions_period_symbol TO uq_accounting_contributions_period_symbol;
ALTER TABLE public.accounting_holdings RENAME CONSTRAINT uq_olympus_accounting_holdings_period_symbol TO uq_accounting_holdings_period_symbol;
ALTER TABLE public.accounting_periods RENAME CONSTRAINT uq_olympus_accounting_periods_id_period_date TO uq_accounting_periods_id_period_date;
ALTER TABLE public.action_cost_outcomes RENAME CONSTRAINT uq_olympus_action_cost_outcomes_estimate_execution TO uq_action_cost_outcomes_estimate_execution;
ALTER TABLE public.attention_decisions RENAME CONSTRAINT uq_olympus_attention_decisions_plan_target TO uq_attention_decisions_plan_target;
ALTER TABLE public.attention_plans RENAME CONSTRAINT uq_olympus_attention_plans_run_attempt TO uq_attention_plans_run_attempt;
ALTER TABLE public.gate_evaluations RENAME CONSTRAINT uq_olympus_gate_evaluations_content_hash TO uq_gate_evaluations_content_hash;
ALTER TABLE public.policy_comparison_reports RENAME CONSTRAINT uq_olympus_policy_comparison_reports_content_hash TO uq_policy_comparison_reports_content_hash;
ALTER TABLE public.provider_attempts RENAME CONSTRAINT uq_olympus_provider_attempts_sequence TO uq_provider_attempts_sequence;
ALTER TABLE public.replay_arm_results RENAME CONSTRAINT uq_olympus_replay_arm_results_run_arm TO uq_replay_arm_results_run_arm;
ALTER TABLE public.replay_input_manifests RENAME CONSTRAINT uq_olympus_replay_input_manifests_content_hash TO uq_replay_input_manifests_content_hash;
ALTER TABLE public.replay_pairs RENAME CONSTRAINT uq_olympus_replay_pairs_content_hash TO uq_replay_pairs_content_hash;
ALTER TABLE public.replay_run_events RENAME CONSTRAINT uq_olympus_replay_run_events_run_sequence TO uq_replay_run_events_run_sequence;
ALTER TABLE public.ticker_evidence_bundles RENAME CONSTRAINT uq_olympus_ticker_evidence_bundles_run_ticker TO uq_ticker_evidence_bundles_run_ticker;
ALTER TABLE public.ticker_evidence_bundles RENAME CONSTRAINT uq_olympus_ticker_evidence_bundles_run_ticker_content TO uq_ticker_evidence_bundles_run_ticker_content;

-- ---------------------------------------------------------------------------
-- 9. Rename the 93 triggers (no alias is possible; the table
--    name is the already-renamed one).
-- ---------------------------------------------------------------------------
ALTER TRIGGER reject_olympus_accounting_contributions_mutation ON public.accounting_contributions RENAME TO reject_accounting_contributions_mutation;
ALTER TRIGGER reject_olympus_accounting_contributions_truncate ON public.accounting_contributions RENAME TO reject_accounting_contributions_truncate;
ALTER TRIGGER reject_olympus_accounting_holdings_mutation ON public.accounting_holdings RENAME TO reject_accounting_holdings_mutation;
ALTER TRIGGER reject_olympus_accounting_holdings_truncate ON public.accounting_holdings RENAME TO reject_accounting_holdings_truncate;
ALTER TRIGGER reject_olympus_accounting_periods_mutation ON public.accounting_periods RENAME TO reject_accounting_periods_mutation;
ALTER TRIGGER reject_olympus_accounting_periods_truncate ON public.accounting_periods RENAME TO reject_accounting_periods_truncate;
ALTER TRIGGER reject_olympus_action_cost_estimates_mutation ON public.action_cost_estimates RENAME TO reject_action_cost_estimates_mutation;
ALTER TRIGGER reject_olympus_action_cost_estimates_truncate ON public.action_cost_estimates RENAME TO reject_action_cost_estimates_truncate;
ALTER TRIGGER reject_olympus_action_cost_outcomes_mutation ON public.action_cost_outcomes RENAME TO reject_action_cost_outcomes_mutation;
ALTER TRIGGER reject_olympus_action_cost_outcomes_truncate ON public.action_cost_outcomes RENAME TO reject_action_cost_outcomes_truncate;
ALTER TRIGGER reject_olympus_attention_context_manifests_mutation ON public.attention_context_manifests RENAME TO reject_attention_context_manifests_mutation;
ALTER TRIGGER reject_olympus_attention_context_manifests_truncate ON public.attention_context_manifests RENAME TO reject_attention_context_manifests_truncate;
ALTER TRIGGER reject_olympus_attention_decision_attempts_mutation ON public.attention_decision_attempts RENAME TO reject_attention_decision_attempts_mutation;
ALTER TRIGGER reject_olympus_attention_decision_attempts_truncate ON public.attention_decision_attempts RENAME TO reject_attention_decision_attempts_truncate;
ALTER TRIGGER reject_olympus_attention_decisions_mutation ON public.attention_decisions RENAME TO reject_attention_decisions_mutation;
ALTER TRIGGER reject_olympus_attention_decisions_truncate ON public.attention_decisions RENAME TO reject_attention_decisions_truncate;
ALTER TRIGGER reject_olympus_attention_plans_mutation ON public.attention_plans RENAME TO reject_attention_plans_mutation;
ALTER TRIGGER reject_olympus_attention_plans_truncate ON public.attention_plans RENAME TO reject_attention_plans_truncate;
ALTER TRIGGER reject_olympus_attention_policy_evaluations_mutation ON public.attention_policy_evaluations RENAME TO reject_attention_policy_evaluations_mutation;
ALTER TRIGGER reject_olympus_attention_policy_evaluations_truncate ON public.attention_policy_evaluations RENAME TO reject_attention_policy_evaluations_truncate;
ALTER TRIGGER reject_olympus_calibrated_forecasts_mutation ON public.calibrated_forecasts RENAME TO reject_calibrated_forecasts_mutation;
ALTER TRIGGER reject_olympus_calibrated_forecasts_truncate ON public.calibrated_forecasts RENAME TO reject_calibrated_forecasts_truncate;
ALTER TRIGGER reject_olympus_component_attribution_reports_mutation ON public.component_attribution_reports RENAME TO reject_component_attribution_reports_mutation;
ALTER TRIGGER reject_olympus_component_attribution_reports_truncate ON public.component_attribution_reports RENAME TO reject_component_attribution_reports_truncate;
ALTER TRIGGER reject_olympus_covariance_snapshots_mutation ON public.covariance_snapshots RENAME TO reject_covariance_snapshots_mutation;
ALTER TRIGGER reject_olympus_covariance_snapshots_truncate ON public.covariance_snapshots RENAME TO reject_covariance_snapshots_truncate;
ALTER TRIGGER reject_olympus_evidence_amendment_base_mismatch ON public.evidence_bundle_amendments RENAME TO reject_evidence_amendment_base_mismatch;
ALTER TRIGGER reject_olympus_evidence_bundle_amendments_mutation ON public.evidence_bundle_amendments RENAME TO reject_evidence_bundle_amendments_mutation;
ALTER TRIGGER reject_olympus_evidence_bundle_amendments_truncate ON public.evidence_bundle_amendments RENAME TO reject_evidence_bundle_amendments_truncate;
ALTER TRIGGER reject_olympus_forecast_amendments_mutation ON public.forecast_amendments RENAME TO reject_forecast_amendments_mutation;
ALTER TRIGGER reject_olympus_forecast_amendments_truncate ON public.forecast_amendments RENAME TO reject_forecast_amendments_truncate;
ALTER TRIGGER reject_olympus_forecast_assessments_mutation ON public.forecast_assessments RENAME TO reject_forecast_assessments_mutation;
ALTER TRIGGER reject_olympus_forecast_assessments_truncate ON public.forecast_assessments RENAME TO reject_forecast_assessments_truncate;
ALTER TRIGGER reject_olympus_forecast_calibrations_mutation ON public.forecast_calibrations RENAME TO reject_forecast_calibrations_mutation;
ALTER TRIGGER reject_olympus_forecast_calibrations_truncate ON public.forecast_calibrations RENAME TO reject_forecast_calibrations_truncate;
ALTER TRIGGER reject_olympus_forecast_outcomes_mutation ON public.forecast_outcomes RENAME TO reject_forecast_outcomes_mutation;
ALTER TRIGGER reject_olympus_forecast_outcomes_truncate ON public.forecast_outcomes RENAME TO reject_forecast_outcomes_truncate;
ALTER TRIGGER reject_olympus_gate_criteria_versions_mutation ON public.gate_criteria_versions RENAME TO reject_gate_criteria_versions_mutation;
ALTER TRIGGER reject_olympus_gate_criteria_versions_truncate ON public.gate_criteria_versions RENAME TO reject_gate_criteria_versions_truncate;
ALTER TRIGGER reject_olympus_gate_evaluations_mutation ON public.gate_evaluations RENAME TO reject_gate_evaluations_mutation;
ALTER TRIGGER reject_olympus_gate_evaluations_truncate ON public.gate_evaluations RENAME TO reject_gate_evaluations_truncate;
ALTER TRIGGER reject_olympus_h8_risk_run_refs_mutation ON public.h8_risk_run_refs RENAME TO reject_h8_risk_run_refs_mutation;
ALTER TRIGGER reject_olympus_h8_risk_run_refs_truncate ON public.h8_risk_run_refs RENAME TO reject_h8_risk_run_refs_truncate;
ALTER TRIGGER reject_olympus_liquidity_snapshots_mutation ON public.liquidity_snapshots RENAME TO reject_liquidity_snapshots_mutation;
ALTER TRIGGER reject_olympus_liquidity_snapshots_truncate ON public.liquidity_snapshots RENAME TO reject_liquidity_snapshots_truncate;
ALTER TRIGGER reject_olympus_missing_fact_requests_mutation ON public.missing_fact_requests RENAME TO reject_missing_fact_requests_mutation;
ALTER TRIGGER reject_olympus_missing_fact_requests_truncate ON public.missing_fact_requests RENAME TO reject_missing_fact_requests_truncate;
ALTER TRIGGER reject_olympus_node_runs_mutation ON public.node_runs RENAME TO reject_node_runs_mutation;
ALTER TRIGGER reject_olympus_node_runs_truncate ON public.node_runs RENAME TO reject_node_runs_truncate;
ALTER TRIGGER reject_olympus_outcome_episodes_mutation ON public.outcome_episodes RENAME TO reject_outcome_episodes_mutation;
ALTER TRIGGER reject_olympus_outcome_episodes_truncate ON public.outcome_episodes RENAME TO reject_outcome_episodes_truncate;
ALTER TRIGGER reject_olympus_outcome_lesson_versions_mutation ON public.outcome_lesson_versions RENAME TO reject_outcome_lesson_versions_mutation;
ALTER TRIGGER reject_olympus_outcome_lesson_versions_truncate ON public.outcome_lesson_versions RENAME TO reject_outcome_lesson_versions_truncate;
ALTER TRIGGER reject_olympus_policy_comparison_reports_mutation ON public.policy_comparison_reports RENAME TO reject_policy_comparison_reports_mutation;
ALTER TRIGGER reject_olympus_policy_comparison_reports_truncate ON public.policy_comparison_reports RENAME TO reject_policy_comparison_reports_truncate;
ALTER TRIGGER reject_olympus_policy_governance_decisions_mutation ON public.policy_governance_decisions RENAME TO reject_policy_governance_decisions_mutation;
ALTER TRIGGER reject_olympus_policy_governance_decisions_truncate ON public.policy_governance_decisions RENAME TO reject_policy_governance_decisions_truncate;
ALTER TRIGGER reject_olympus_pretrade_risk_reports_mutation ON public.pretrade_risk_reports RENAME TO reject_pretrade_risk_reports_mutation;
ALTER TRIGGER reject_olympus_pretrade_risk_reports_truncate ON public.pretrade_risk_reports RENAME TO reject_pretrade_risk_reports_truncate;
ALTER TRIGGER reject_olympus_profile_config_mutation ON public.profile_config RENAME TO reject_profile_config_mutation;
ALTER TRIGGER reject_olympus_profile_config_truncate ON public.profile_config RENAME TO reject_profile_config_truncate;
ALTER TRIGGER reject_olympus_provider_attempts_mutation ON public.provider_attempts RENAME TO reject_provider_attempts_mutation;
ALTER TRIGGER reject_olympus_provider_attempts_truncate ON public.provider_attempts RENAME TO reject_provider_attempts_truncate;
ALTER TRIGGER reject_olympus_provider_calls_mutation ON public.provider_calls RENAME TO reject_provider_calls_mutation;
ALTER TRIGGER reject_olympus_provider_calls_truncate ON public.provider_calls RENAME TO reject_provider_calls_truncate;
ALTER TRIGGER reject_olympus_replay_arm_results_mutation ON public.replay_arm_results RENAME TO reject_replay_arm_results_mutation;
ALTER TRIGGER reject_olympus_replay_arm_results_truncate ON public.replay_arm_results RENAME TO reject_replay_arm_results_truncate;
ALTER TRIGGER reject_olympus_replay_input_manifests_mutation ON public.replay_input_manifests RENAME TO reject_replay_input_manifests_mutation;
ALTER TRIGGER reject_olympus_replay_input_manifests_truncate ON public.replay_input_manifests RENAME TO reject_replay_input_manifests_truncate;
ALTER TRIGGER reject_olympus_replay_pairs_mutation ON public.replay_pairs RENAME TO reject_replay_pairs_mutation;
ALTER TRIGGER reject_olympus_replay_pairs_truncate ON public.replay_pairs RENAME TO reject_replay_pairs_truncate;
ALTER TRIGGER reject_olympus_replay_run_events_mutation ON public.replay_run_events RENAME TO reject_replay_run_events_mutation;
ALTER TRIGGER reject_olympus_replay_run_events_truncate ON public.replay_run_events RENAME TO reject_replay_run_events_truncate;
ALTER TRIGGER reject_olympus_research_belief_versions_mutation ON public.research_belief_versions RENAME TO reject_research_belief_versions_mutation;
ALTER TRIGGER reject_olympus_research_belief_versions_truncate ON public.research_belief_versions RENAME TO reject_research_belief_versions_truncate;
ALTER TRIGGER reject_olympus_research_corpus_mutation ON public.research_corpus RENAME TO reject_research_corpus_mutation;
ALTER TRIGGER reject_olympus_research_corpus_truncate ON public.research_corpus RENAME TO reject_research_corpus_truncate;
ALTER TRIGGER reject_olympus_research_evidence_mutation ON public.research_evidence RENAME TO reject_research_evidence_mutation;
ALTER TRIGGER reject_olympus_research_evidence_truncate ON public.research_evidence RENAME TO reject_research_evidence_truncate;
ALTER TRIGGER reject_olympus_research_expected_event_versions_mutation ON public.research_expected_event_versions RENAME TO reject_research_expected_event_versions_mutation;
ALTER TRIGGER reject_olympus_research_expected_event_versions_truncate ON public.research_expected_event_versions RENAME TO reject_research_expected_event_versions_truncate;
ALTER TRIGGER reject_olympus_research_legacy_refs_mutation ON public.research_legacy_refs RENAME TO reject_research_legacy_refs_mutation;
ALTER TRIGGER reject_olympus_research_legacy_refs_truncate ON public.research_legacy_refs RENAME TO reject_research_legacy_refs_truncate;
ALTER TRIGGER reject_olympus_research_patches_mutation ON public.research_patches RENAME TO reject_research_patches_mutation;
ALTER TRIGGER reject_olympus_research_patches_truncate ON public.research_patches RENAME TO reject_research_patches_truncate;
ALTER TRIGGER reject_olympus_research_state_pins_mutation ON public.research_state_pins RENAME TO reject_research_state_pins_mutation;
ALTER TRIGGER reject_olympus_research_state_pins_truncate ON public.research_state_pins RENAME TO reject_research_state_pins_truncate;
ALTER TRIGGER reject_olympus_research_state_versions_mutation ON public.research_state_versions RENAME TO reject_research_state_versions_mutation;
ALTER TRIGGER reject_olympus_research_state_versions_truncate ON public.research_state_versions RENAME TO reject_research_state_versions_truncate;
ALTER TRIGGER reject_olympus_risk_policies_mutation ON public.risk_policies RENAME TO reject_risk_policies_mutation;
ALTER TRIGGER reject_olympus_risk_policies_truncate ON public.risk_policies RENAME TO reject_risk_policies_truncate;
ALTER TRIGGER reject_olympus_ticker_evidence_bundles_mutation ON public.ticker_evidence_bundles RENAME TO reject_ticker_evidence_bundles_mutation;
ALTER TRIGGER reject_olympus_ticker_evidence_bundles_truncate ON public.ticker_evidence_bundles RENAME TO reject_ticker_evidence_bundles_truncate;

