-- 132_rename_phase_a_compat_views.sql
-- Phase A of the `olympus_*` terminology removal (#4295 gap G5).
--
-- ADDITIVE ONLY. This migration does not rename, alter, or drop any existing
-- object. It creates new-name compatibility views over the current `olympus_*`
-- base tables/views so application code can switch to the new names while the
-- underlying objects keep their old names.
--
-- Phase B (a later, human-approved migration) renames the base objects and
-- recreates old-name compatibility views. Phase C drops the old-name views once
-- `main` runs the new code. Neither is in this file.
--
-- Why views and not a rename here: code and migration land on `main` in the same
-- push, but db-migrate pauses on the `production` environment for human approval.
-- A rename-only migration would leave new-name code running against the old
-- schema in that window (PostgREST PGRST205). New-name views close the window.
--
-- `security_invoker = true` is MANDATORY on every base-table compatibility view.
-- The PostgreSQL default (false) runs the view as its owner and bypasses the
-- base table's RLS policies -- the `atlas_run_health` unauthenticated-DELETE
-- defect documented at digiquant/supabase/README.md. The per-object grants below
-- mirror the CURRENT effective state of the base objects, including the later
-- tightening in `129_tighten_anon_read.sql` (anon keeps SELECT on
-- olympus_run_event_trace but was revoked from the two position_events views).
--
-- Replay-safe: unwrapped (the db-migrate loop runs this file plus its ledger
-- INSERT inside one transaction), and uses only CREATE OR REPLACE / REVOKE /
-- GRANT. Never touches `olympus_schema_migrations`.

-- ---------------------------------------------------------------------------
-- 42 base tables -> service_role SELECT + INSERT (default posture)
-- ---------------------------------------------------------------------------
CREATE OR REPLACE VIEW public.node_runs WITH (security_invoker = true) AS
SELECT * FROM public.olympus_node_runs;
REVOKE ALL ON public.node_runs FROM PUBLIC, anon, authenticated, service_role;
GRANT SELECT, INSERT ON public.node_runs TO service_role;

CREATE OR REPLACE VIEW public.provider_calls WITH (security_invoker = true) AS
SELECT * FROM public.olympus_provider_calls;
REVOKE ALL ON public.provider_calls FROM PUBLIC, anon, authenticated, service_role;
GRANT SELECT, INSERT ON public.provider_calls TO service_role;

CREATE OR REPLACE VIEW public.provider_attempts WITH (security_invoker = true) AS
SELECT * FROM public.olympus_provider_attempts;
REVOKE ALL ON public.provider_attempts FROM PUBLIC, anon, authenticated, service_role;
GRANT SELECT, INSERT ON public.provider_attempts TO service_role;

CREATE OR REPLACE VIEW public.research_corpus WITH (security_invoker = true) AS
SELECT * FROM public.olympus_research_corpus;
REVOKE ALL ON public.research_corpus FROM PUBLIC, anon, authenticated, service_role;
GRANT SELECT, INSERT ON public.research_corpus TO service_role;

CREATE OR REPLACE VIEW public.forecast_assessments WITH (security_invoker = true) AS
SELECT * FROM public.olympus_forecast_assessments;
REVOKE ALL ON public.forecast_assessments FROM PUBLIC, anon, authenticated, service_role;
GRANT SELECT, INSERT ON public.forecast_assessments TO service_role;

CREATE OR REPLACE VIEW public.forecast_amendments WITH (security_invoker = true) AS
SELECT * FROM public.olympus_forecast_amendments;
REVOKE ALL ON public.forecast_amendments FROM PUBLIC, anon, authenticated, service_role;
GRANT SELECT, INSERT ON public.forecast_amendments TO service_role;

CREATE OR REPLACE VIEW public.forecast_outcomes WITH (security_invoker = true) AS
SELECT * FROM public.olympus_forecast_outcomes;
REVOKE ALL ON public.forecast_outcomes FROM PUBLIC, anon, authenticated, service_role;
GRANT SELECT, INSERT ON public.forecast_outcomes TO service_role;

CREATE OR REPLACE VIEW public.forecast_calibrations WITH (security_invoker = true) AS
SELECT * FROM public.olympus_forecast_calibrations;
REVOKE ALL ON public.forecast_calibrations FROM PUBLIC, anon, authenticated, service_role;
GRANT SELECT, INSERT ON public.forecast_calibrations TO service_role;

CREATE OR REPLACE VIEW public.calibrated_forecasts WITH (security_invoker = true) AS
SELECT * FROM public.olympus_calibrated_forecasts;
REVOKE ALL ON public.calibrated_forecasts FROM PUBLIC, anon, authenticated, service_role;
GRANT SELECT, INSERT ON public.calibrated_forecasts TO service_role;

CREATE OR REPLACE VIEW public.risk_policies WITH (security_invoker = true) AS
SELECT * FROM public.olympus_risk_policies;
REVOKE ALL ON public.risk_policies FROM PUBLIC, anon, authenticated, service_role;
GRANT SELECT, INSERT ON public.risk_policies TO service_role;

CREATE OR REPLACE VIEW public.covariance_snapshots WITH (security_invoker = true) AS
SELECT * FROM public.olympus_covariance_snapshots;
REVOKE ALL ON public.covariance_snapshots FROM PUBLIC, anon, authenticated, service_role;
GRANT SELECT, INSERT ON public.covariance_snapshots TO service_role;

CREATE OR REPLACE VIEW public.h8_risk_run_refs WITH (security_invoker = true) AS
SELECT * FROM public.olympus_h8_risk_run_refs;
REVOKE ALL ON public.h8_risk_run_refs FROM PUBLIC, anon, authenticated, service_role;
GRANT SELECT, INSERT ON public.h8_risk_run_refs TO service_role;

CREATE OR REPLACE VIEW public.liquidity_snapshots WITH (security_invoker = true) AS
SELECT * FROM public.olympus_liquidity_snapshots;
REVOKE ALL ON public.liquidity_snapshots FROM PUBLIC, anon, authenticated, service_role;
GRANT SELECT, INSERT ON public.liquidity_snapshots TO service_role;

CREATE OR REPLACE VIEW public.action_cost_estimates WITH (security_invoker = true) AS
SELECT * FROM public.olympus_action_cost_estimates;
REVOKE ALL ON public.action_cost_estimates FROM PUBLIC, anon, authenticated, service_role;
GRANT SELECT, INSERT ON public.action_cost_estimates TO service_role;

CREATE OR REPLACE VIEW public.action_cost_outcomes WITH (security_invoker = true) AS
SELECT * FROM public.olympus_action_cost_outcomes;
REVOKE ALL ON public.action_cost_outcomes FROM PUBLIC, anon, authenticated, service_role;
GRANT SELECT, INSERT ON public.action_cost_outcomes TO service_role;

CREATE OR REPLACE VIEW public.pretrade_risk_reports WITH (security_invoker = true) AS
SELECT * FROM public.olympus_pretrade_risk_reports;
REVOKE ALL ON public.pretrade_risk_reports FROM PUBLIC, anon, authenticated, service_role;
GRANT SELECT, INSERT ON public.pretrade_risk_reports TO service_role;

CREATE OR REPLACE VIEW public.research_evidence WITH (security_invoker = true) AS
SELECT * FROM public.olympus_research_evidence;
REVOKE ALL ON public.research_evidence FROM PUBLIC, anon, authenticated, service_role;
GRANT SELECT, INSERT ON public.research_evidence TO service_role;

CREATE OR REPLACE VIEW public.research_belief_versions WITH (security_invoker = true) AS
SELECT * FROM public.olympus_research_belief_versions;
REVOKE ALL ON public.research_belief_versions FROM PUBLIC, anon, authenticated, service_role;
GRANT SELECT, INSERT ON public.research_belief_versions TO service_role;

CREATE OR REPLACE VIEW public.research_expected_event_versions WITH (security_invoker = true) AS
SELECT * FROM public.olympus_research_expected_event_versions;
REVOKE ALL ON public.research_expected_event_versions FROM PUBLIC, anon, authenticated, service_role;
GRANT SELECT, INSERT ON public.research_expected_event_versions TO service_role;

CREATE OR REPLACE VIEW public.research_patches WITH (security_invoker = true) AS
SELECT * FROM public.olympus_research_patches;
REVOKE ALL ON public.research_patches FROM PUBLIC, anon, authenticated, service_role;
GRANT SELECT, INSERT ON public.research_patches TO service_role;

CREATE OR REPLACE VIEW public.research_legacy_refs WITH (security_invoker = true) AS
SELECT * FROM public.olympus_research_legacy_refs;
REVOKE ALL ON public.research_legacy_refs FROM PUBLIC, anon, authenticated, service_role;
GRANT SELECT, INSERT ON public.research_legacy_refs TO service_role;

CREATE OR REPLACE VIEW public.research_state_versions WITH (security_invoker = true) AS
SELECT * FROM public.olympus_research_state_versions;
REVOKE ALL ON public.research_state_versions FROM PUBLIC, anon, authenticated, service_role;
GRANT SELECT, INSERT ON public.research_state_versions TO service_role;

CREATE OR REPLACE VIEW public.research_state_pins WITH (security_invoker = true) AS
SELECT * FROM public.olympus_research_state_pins;
REVOKE ALL ON public.research_state_pins FROM PUBLIC, anon, authenticated, service_role;
GRANT SELECT, INSERT ON public.research_state_pins TO service_role;

CREATE OR REPLACE VIEW public.ticker_evidence_bundles WITH (security_invoker = true) AS
SELECT * FROM public.olympus_ticker_evidence_bundles;
REVOKE ALL ON public.ticker_evidence_bundles FROM PUBLIC, anon, authenticated, service_role;
GRANT SELECT, INSERT ON public.ticker_evidence_bundles TO service_role;

CREATE OR REPLACE VIEW public.missing_fact_requests WITH (security_invoker = true) AS
SELECT * FROM public.olympus_missing_fact_requests;
REVOKE ALL ON public.missing_fact_requests FROM PUBLIC, anon, authenticated, service_role;
GRANT SELECT, INSERT ON public.missing_fact_requests TO service_role;

CREATE OR REPLACE VIEW public.evidence_bundle_amendments WITH (security_invoker = true) AS
SELECT * FROM public.olympus_evidence_bundle_amendments;
REVOKE ALL ON public.evidence_bundle_amendments FROM PUBLIC, anon, authenticated, service_role;
GRANT SELECT, INSERT ON public.evidence_bundle_amendments TO service_role;

CREATE OR REPLACE VIEW public.attention_plans WITH (security_invoker = true) AS
SELECT * FROM public.olympus_attention_plans;
REVOKE ALL ON public.attention_plans FROM PUBLIC, anon, authenticated, service_role;
GRANT SELECT, INSERT ON public.attention_plans TO service_role;

CREATE OR REPLACE VIEW public.attention_decisions WITH (security_invoker = true) AS
SELECT * FROM public.olympus_attention_decisions;
REVOKE ALL ON public.attention_decisions FROM PUBLIC, anon, authenticated, service_role;
GRANT SELECT, INSERT ON public.attention_decisions TO service_role;

CREATE OR REPLACE VIEW public.attention_decision_attempts WITH (security_invoker = true) AS
SELECT * FROM public.olympus_attention_decision_attempts;
REVOKE ALL ON public.attention_decision_attempts FROM PUBLIC, anon, authenticated, service_role;
GRANT SELECT, INSERT ON public.attention_decision_attempts TO service_role;

CREATE OR REPLACE VIEW public.attention_context_manifests WITH (security_invoker = true) AS
SELECT * FROM public.olympus_attention_context_manifests;
REVOKE ALL ON public.attention_context_manifests FROM PUBLIC, anon, authenticated, service_role;
GRANT SELECT, INSERT ON public.attention_context_manifests TO service_role;

CREATE OR REPLACE VIEW public.attention_policy_evaluations WITH (security_invoker = true) AS
SELECT * FROM public.olympus_attention_policy_evaluations;
REVOKE ALL ON public.attention_policy_evaluations FROM PUBLIC, anon, authenticated, service_role;
GRANT SELECT, INSERT ON public.attention_policy_evaluations TO service_role;

CREATE OR REPLACE VIEW public.outcome_episodes WITH (security_invoker = true) AS
SELECT * FROM public.olympus_outcome_episodes;
REVOKE ALL ON public.outcome_episodes FROM PUBLIC, anon, authenticated, service_role;
GRANT SELECT, INSERT ON public.outcome_episodes TO service_role;

CREATE OR REPLACE VIEW public.component_attribution_reports WITH (security_invoker = true) AS
SELECT * FROM public.olympus_component_attribution_reports;
REVOKE ALL ON public.component_attribution_reports FROM PUBLIC, anon, authenticated, service_role;
GRANT SELECT, INSERT ON public.component_attribution_reports TO service_role;

CREATE OR REPLACE VIEW public.outcome_lesson_versions WITH (security_invoker = true) AS
SELECT * FROM public.olympus_outcome_lesson_versions;
REVOKE ALL ON public.outcome_lesson_versions FROM PUBLIC, anon, authenticated, service_role;
GRANT SELECT, INSERT ON public.outcome_lesson_versions TO service_role;

CREATE OR REPLACE VIEW public.replay_input_manifests WITH (security_invoker = true) AS
SELECT * FROM public.olympus_replay_input_manifests;
REVOKE ALL ON public.replay_input_manifests FROM PUBLIC, anon, authenticated, service_role;
GRANT SELECT, INSERT ON public.replay_input_manifests TO service_role;

CREATE OR REPLACE VIEW public.replay_pairs WITH (security_invoker = true) AS
SELECT * FROM public.olympus_replay_pairs;
REVOKE ALL ON public.replay_pairs FROM PUBLIC, anon, authenticated, service_role;
GRANT SELECT, INSERT ON public.replay_pairs TO service_role;

CREATE OR REPLACE VIEW public.replay_run_events WITH (security_invoker = true) AS
SELECT * FROM public.olympus_replay_run_events;
REVOKE ALL ON public.replay_run_events FROM PUBLIC, anon, authenticated, service_role;
GRANT SELECT, INSERT ON public.replay_run_events TO service_role;

CREATE OR REPLACE VIEW public.replay_arm_results WITH (security_invoker = true) AS
SELECT * FROM public.olympus_replay_arm_results;
REVOKE ALL ON public.replay_arm_results FROM PUBLIC, anon, authenticated, service_role;
GRANT SELECT, INSERT ON public.replay_arm_results TO service_role;

CREATE OR REPLACE VIEW public.policy_comparison_reports WITH (security_invoker = true) AS
SELECT * FROM public.olympus_policy_comparison_reports;
REVOKE ALL ON public.policy_comparison_reports FROM PUBLIC, anon, authenticated, service_role;
GRANT SELECT, INSERT ON public.policy_comparison_reports TO service_role;

CREATE OR REPLACE VIEW public.gate_criteria_versions WITH (security_invoker = true) AS
SELECT * FROM public.olympus_gate_criteria_versions;
REVOKE ALL ON public.gate_criteria_versions FROM PUBLIC, anon, authenticated, service_role;
GRANT SELECT, INSERT ON public.gate_criteria_versions TO service_role;

CREATE OR REPLACE VIEW public.gate_evaluations WITH (security_invoker = true) AS
SELECT * FROM public.olympus_gate_evaluations;
REVOKE ALL ON public.gate_evaluations FROM PUBLIC, anon, authenticated, service_role;
GRANT SELECT, INSERT ON public.gate_evaluations TO service_role;

CREATE OR REPLACE VIEW public.policy_governance_decisions WITH (security_invoker = true) AS
SELECT * FROM public.olympus_policy_governance_decisions;
REVOKE ALL ON public.policy_governance_decisions FROM PUBLIC, anon, authenticated, service_role;
GRANT SELECT, INSERT ON public.policy_governance_decisions TO service_role;

-- ---------------------------------------------------------------------------
-- 4 base tables with an added authenticated SELECT (migration 098)
-- ---------------------------------------------------------------------------
CREATE OR REPLACE VIEW public.accounting_periods WITH (security_invoker = true) AS
SELECT * FROM public.olympus_accounting_periods;
REVOKE ALL ON public.accounting_periods FROM PUBLIC, anon, authenticated, service_role;
GRANT SELECT, INSERT ON public.accounting_periods TO service_role;
GRANT SELECT ON public.accounting_periods TO authenticated;

CREATE OR REPLACE VIEW public.accounting_contributions WITH (security_invoker = true) AS
SELECT * FROM public.olympus_accounting_contributions;
REVOKE ALL ON public.accounting_contributions FROM PUBLIC, anon, authenticated, service_role;
GRANT SELECT, INSERT ON public.accounting_contributions TO service_role;
GRANT SELECT ON public.accounting_contributions TO authenticated;

CREATE OR REPLACE VIEW public.accounting_holdings WITH (security_invoker = true) AS
SELECT * FROM public.olympus_accounting_holdings;
REVOKE ALL ON public.accounting_holdings FROM PUBLIC, anon, authenticated, service_role;
GRANT SELECT, INSERT ON public.accounting_holdings TO service_role;
GRANT SELECT ON public.accounting_holdings TO authenticated;

CREATE OR REPLACE VIEW public.profile_config WITH (security_invoker = true) AS
SELECT * FROM public.olympus_profile_config;
REVOKE ALL ON public.profile_config FROM PUBLIC, anon, authenticated, service_role;
GRANT SELECT, INSERT ON public.profile_config TO service_role;
GRANT SELECT ON public.profile_config TO authenticated;

-- ---------------------------------------------------------------------------
-- run_events: mutable telemetry (no append-only trigger on 066). The
-- diagnostics writer does an explicit delete-then-insert (PostgreSQL cannot run
-- INSERT ... ON CONFLICT through a view), so service_role needs DELETE here to
-- mirror the base-table default-privilege posture. Never anon/authenticated.
-- ---------------------------------------------------------------------------
CREATE OR REPLACE VIEW public.run_events WITH (security_invoker = true) AS
SELECT * FROM public.olympus_run_events;
REVOKE ALL ON public.run_events FROM PUBLIC, anon, authenticated, service_role;
GRANT SELECT, INSERT, DELETE ON public.run_events TO service_role;

-- ---------------------------------------------------------------------------
-- 3 existing views -> new-name views preserving the ORIGINAL security_invoker
-- setting and the current effective grants. `olympus_position_events` cannot
-- become `position_events` (base table since migration 001); it becomes
-- `position_events_labeled`.
-- ---------------------------------------------------------------------------
CREATE OR REPLACE VIEW public.run_event_trace WITH (security_invoker = false) AS
SELECT * FROM public.olympus_run_event_trace;
REVOKE ALL ON public.run_event_trace FROM PUBLIC, anon, authenticated, service_role;
GRANT SELECT ON public.run_event_trace TO anon, authenticated, service_role;

CREATE OR REPLACE VIEW public.position_events_labeled WITH (security_invoker = true) AS
SELECT * FROM public.olympus_position_events;
REVOKE ALL ON public.position_events_labeled FROM PUBLIC, anon, authenticated, service_role;
GRANT SELECT ON public.position_events_labeled TO authenticated, service_role;

CREATE OR REPLACE VIEW public.position_events_authoritative WITH (security_invoker = true) AS
SELECT * FROM public.olympus_position_events_authoritative;
REVOKE ALL ON public.position_events_authoritative FROM PUBLIC, anon, authenticated, service_role;
GRANT SELECT ON public.position_events_authoritative TO authenticated, service_role;
