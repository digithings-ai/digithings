-- Append-only guards for D1 (SQLite).
--
-- GENERATED FILE - DO NOT EDIT BY HAND.
-- Source of truth: scripts/gen_d1_reject_guards.py, which reads
-- digiquant/supabase/migrations/*.sql. Run it after touching a migration.
--
-- Ticket: DIG-2894 (supabase exit 6). Reviewer: DIG-2892 (exit 4).
--
-- The Postgres guards are BEFORE UPDATE OR DELETE ... FOR EACH ROW, i.e.
-- append-only: INSERT stays legal and corrections must INSERT a superseding
-- row. Each guard function's own RAISE EXCEPTION text is reused verbatim so
-- the D1 runtime reports the same operator-facing message.

-- Guard functions ported: 19
-- Guarded tables:         60
-- D1 row triggers:       118
-- Worker-side obligations (no SQLite equivalent): 61

BEGIN TRANSACTION;

-- broker_connections: append-only via reject_broker_connection_credential_mutation in Postgres.
CREATE TRIGGER IF NOT EXISTS "broker_connections_append_only_update"
BEFORE UPDATE ON "broker_connections"
BEGIN
  SELECT RAISE(ABORT, 'broker_connections is append-only; corrections must INSERT a superseding row');
END;

-- broker_executions: append-only via reject_broker_mirror_mutation in Postgres.
CREATE TRIGGER IF NOT EXISTS "broker_executions_append_only_delete"
BEFORE DELETE ON "broker_executions"
BEGIN
  SELECT RAISE(ABORT, 'broker_executions is append-only; corrections must INSERT a superseding row');
END;
CREATE TRIGGER IF NOT EXISTS "broker_executions_append_only_update"
BEFORE UPDATE ON "broker_executions"
BEGIN
  SELECT RAISE(ABORT, 'broker_executions is append-only; corrections must INSERT a superseding row');
END;

-- broker_orders: append-only via reject_broker_mirror_mutation in Postgres.
CREATE TRIGGER IF NOT EXISTS "broker_orders_append_only_delete"
BEFORE DELETE ON "broker_orders"
BEGIN
  SELECT RAISE(ABORT, 'broker_orders is append-only; corrections must INSERT a superseding row');
END;
CREATE TRIGGER IF NOT EXISTS "broker_orders_append_only_update"
BEFORE UPDATE ON "broker_orders"
BEGIN
  SELECT RAISE(ABORT, 'broker_orders is append-only; corrections must INSERT a superseding row');
END;

-- broker_position_snapshots: append-only via reject_broker_mirror_mutation in Postgres.
CREATE TRIGGER IF NOT EXISTS "broker_position_snapshots_append_only_delete"
BEFORE DELETE ON "broker_position_snapshots"
BEGIN
  SELECT RAISE(ABORT, 'broker_position_snapshots is append-only; corrections must INSERT a superseding row');
END;
CREATE TRIGGER IF NOT EXISTS "broker_position_snapshots_append_only_update"
BEFORE UPDATE ON "broker_position_snapshots"
BEGIN
  SELECT RAISE(ABORT, 'broker_position_snapshots is append-only; corrections must INSERT a superseding row');
END;

-- notification_log: append-only via reject_notification_log_mutation in Postgres.
CREATE TRIGGER IF NOT EXISTS "notification_log_append_only_delete"
BEFORE DELETE ON "notification_log"
BEGIN
  SELECT RAISE(ABORT, 'notification_log is append-only; corrections must INSERT a superseding row');
END;
CREATE TRIGGER IF NOT EXISTS "notification_log_append_only_update"
BEFORE UPDATE ON "notification_log"
BEGIN
  SELECT RAISE(ABORT, 'notification_log is append-only; corrections must INSERT a superseding row');
END;

-- olympus_accounting_contributions: append-only via reject_olympus_accounting_mutation in Postgres.
CREATE TRIGGER IF NOT EXISTS "olympus_accounting_contributions_append_only_delete"
BEFORE DELETE ON "olympus_accounting_contributions"
BEGIN
  SELECT RAISE(ABORT, 'olympus_accounting_contributions is append-only; corrections must INSERT a superseding row');
END;
CREATE TRIGGER IF NOT EXISTS "olympus_accounting_contributions_append_only_update"
BEFORE UPDATE ON "olympus_accounting_contributions"
BEGIN
  SELECT RAISE(ABORT, 'olympus_accounting_contributions is append-only; corrections must INSERT a superseding row');
END;

-- olympus_accounting_holdings: append-only via reject_olympus_accounting_mutation in Postgres.
CREATE TRIGGER IF NOT EXISTS "olympus_accounting_holdings_append_only_delete"
BEFORE DELETE ON "olympus_accounting_holdings"
BEGIN
  SELECT RAISE(ABORT, 'olympus_accounting_holdings is append-only; corrections must INSERT a superseding row');
END;
CREATE TRIGGER IF NOT EXISTS "olympus_accounting_holdings_append_only_update"
BEFORE UPDATE ON "olympus_accounting_holdings"
BEGIN
  SELECT RAISE(ABORT, 'olympus_accounting_holdings is append-only; corrections must INSERT a superseding row');
END;

-- olympus_accounting_periods: append-only via reject_olympus_accounting_mutation in Postgres.
CREATE TRIGGER IF NOT EXISTS "olympus_accounting_periods_append_only_delete"
BEFORE DELETE ON "olympus_accounting_periods"
BEGIN
  SELECT RAISE(ABORT, 'olympus_accounting_periods is append-only; corrections must INSERT a superseding row');
END;
CREATE TRIGGER IF NOT EXISTS "olympus_accounting_periods_append_only_update"
BEFORE UPDATE ON "olympus_accounting_periods"
BEGIN
  SELECT RAISE(ABORT, 'olympus_accounting_periods is append-only; corrections must INSERT a superseding row');
END;

-- olympus_action_cost_estimates: append-only via reject_olympus_cost_liquidity_mutation in Postgres.
CREATE TRIGGER IF NOT EXISTS "olympus_action_cost_estimates_append_only_delete"
BEFORE DELETE ON "olympus_action_cost_estimates"
BEGIN
  SELECT RAISE(ABORT, 'olympus_action_cost_estimates is append-only; corrections must INSERT a superseding row');
END;
CREATE TRIGGER IF NOT EXISTS "olympus_action_cost_estimates_append_only_update"
BEFORE UPDATE ON "olympus_action_cost_estimates"
BEGIN
  SELECT RAISE(ABORT, 'olympus_action_cost_estimates is append-only; corrections must INSERT a superseding row');
END;

-- olympus_action_cost_outcomes: append-only via reject_olympus_cost_liquidity_mutation in Postgres.
CREATE TRIGGER IF NOT EXISTS "olympus_action_cost_outcomes_append_only_delete"
BEFORE DELETE ON "olympus_action_cost_outcomes"
BEGIN
  SELECT RAISE(ABORT, 'olympus_action_cost_outcomes is append-only; corrections must INSERT a superseding row');
END;
CREATE TRIGGER IF NOT EXISTS "olympus_action_cost_outcomes_append_only_update"
BEFORE UPDATE ON "olympus_action_cost_outcomes"
BEGIN
  SELECT RAISE(ABORT, 'olympus_action_cost_outcomes is append-only; corrections must INSERT a superseding row');
END;

-- olympus_attention_context_manifests: append-only via reject_olympus_attention_context_mutation in Postgres.
CREATE TRIGGER IF NOT EXISTS "olympus_attention_context_manifests_append_only_delete"
BEFORE DELETE ON "olympus_attention_context_manifests"
BEGIN
  SELECT RAISE(ABORT, 'olympus_attention_context_manifests is append-only; corrections must INSERT a superseding row');
END;
CREATE TRIGGER IF NOT EXISTS "olympus_attention_context_manifests_append_only_update"
BEFORE UPDATE ON "olympus_attention_context_manifests"
BEGIN
  SELECT RAISE(ABORT, 'olympus_attention_context_manifests is append-only; corrections must INSERT a superseding row');
END;

-- olympus_attention_decision_attempts: append-only via reject_olympus_attention_context_mutation in Postgres.
CREATE TRIGGER IF NOT EXISTS "olympus_attention_decision_attempts_append_only_delete"
BEFORE DELETE ON "olympus_attention_decision_attempts"
BEGIN
  SELECT RAISE(ABORT, 'olympus_attention_decision_attempts is append-only; corrections must INSERT a superseding row');
END;
CREATE TRIGGER IF NOT EXISTS "olympus_attention_decision_attempts_append_only_update"
BEFORE UPDATE ON "olympus_attention_decision_attempts"
BEGIN
  SELECT RAISE(ABORT, 'olympus_attention_decision_attempts is append-only; corrections must INSERT a superseding row');
END;

-- olympus_attention_decisions: append-only via reject_olympus_attention_context_mutation in Postgres.
CREATE TRIGGER IF NOT EXISTS "olympus_attention_decisions_append_only_delete"
BEFORE DELETE ON "olympus_attention_decisions"
BEGIN
  SELECT RAISE(ABORT, 'olympus_attention_decisions is append-only; corrections must INSERT a superseding row');
END;
CREATE TRIGGER IF NOT EXISTS "olympus_attention_decisions_append_only_update"
BEFORE UPDATE ON "olympus_attention_decisions"
BEGIN
  SELECT RAISE(ABORT, 'olympus_attention_decisions is append-only; corrections must INSERT a superseding row');
END;

-- olympus_attention_plans: append-only via reject_olympus_attention_context_mutation in Postgres.
CREATE TRIGGER IF NOT EXISTS "olympus_attention_plans_append_only_delete"
BEFORE DELETE ON "olympus_attention_plans"
BEGIN
  SELECT RAISE(ABORT, 'olympus_attention_plans is append-only; corrections must INSERT a superseding row');
END;
CREATE TRIGGER IF NOT EXISTS "olympus_attention_plans_append_only_update"
BEFORE UPDATE ON "olympus_attention_plans"
BEGIN
  SELECT RAISE(ABORT, 'olympus_attention_plans is append-only; corrections must INSERT a superseding row');
END;

-- olympus_attention_policy_evaluations: append-only via reject_olympus_attention_context_mutation in Postgres.
CREATE TRIGGER IF NOT EXISTS "olympus_attention_policy_evaluations_append_only_delete"
BEFORE DELETE ON "olympus_attention_policy_evaluations"
BEGIN
  SELECT RAISE(ABORT, 'olympus_attention_policy_evaluations is append-only; corrections must INSERT a superseding row');
END;
CREATE TRIGGER IF NOT EXISTS "olympus_attention_policy_evaluations_append_only_update"
BEFORE UPDATE ON "olympus_attention_policy_evaluations"
BEGIN
  SELECT RAISE(ABORT, 'olympus_attention_policy_evaluations is append-only; corrections must INSERT a superseding row');
END;

-- olympus_calibrated_forecasts: append-only via reject_olympus_forecast_calibration_mutation in Postgres.
CREATE TRIGGER IF NOT EXISTS "olympus_calibrated_forecasts_append_only_delete"
BEFORE DELETE ON "olympus_calibrated_forecasts"
BEGIN
  SELECT RAISE(ABORT, 'olympus_calibrated_forecasts is append-only; corrections must INSERT a superseding row');
END;
CREATE TRIGGER IF NOT EXISTS "olympus_calibrated_forecasts_append_only_update"
BEFORE UPDATE ON "olympus_calibrated_forecasts"
BEGIN
  SELECT RAISE(ABORT, 'olympus_calibrated_forecasts is append-only; corrections must INSERT a superseding row');
END;

-- olympus_component_attribution_reports: append-only via reject_olympus_outcome_learning_mutation in Postgres.
CREATE TRIGGER IF NOT EXISTS "olympus_component_attribution_reports_append_only_delete"
BEFORE DELETE ON "olympus_component_attribution_reports"
BEGIN
  SELECT RAISE(ABORT, 'olympus_component_attribution_reports is append-only; corrections must INSERT a superseding row');
END;
CREATE TRIGGER IF NOT EXISTS "olympus_component_attribution_reports_append_only_update"
BEFORE UPDATE ON "olympus_component_attribution_reports"
BEGIN
  SELECT RAISE(ABORT, 'olympus_component_attribution_reports is append-only; corrections must INSERT a superseding row');
END;

-- olympus_covariance_snapshots: append-only via reject_olympus_risk_policy_snapshot_mutation in Postgres.
CREATE TRIGGER IF NOT EXISTS "olympus_covariance_snapshots_append_only_delete"
BEFORE DELETE ON "olympus_covariance_snapshots"
BEGIN
  SELECT RAISE(ABORT, 'olympus_covariance_snapshots is append-only; corrections must INSERT a superseding row');
END;
CREATE TRIGGER IF NOT EXISTS "olympus_covariance_snapshots_append_only_update"
BEFORE UPDATE ON "olympus_covariance_snapshots"
BEGIN
  SELECT RAISE(ABORT, 'olympus_covariance_snapshots is append-only; corrections must INSERT a superseding row');
END;

-- olympus_evidence_bundle_amendments: append-only via reject_olympus_evidence_bundle_mutation in Postgres.
CREATE TRIGGER IF NOT EXISTS "olympus_evidence_bundle_amendments_append_only_delete"
BEFORE DELETE ON "olympus_evidence_bundle_amendments"
BEGIN
  SELECT RAISE(ABORT, 'olympus_evidence_bundle_amendments is append-only; corrections must INSERT a superseding row');
END;
CREATE TRIGGER IF NOT EXISTS "olympus_evidence_bundle_amendments_append_only_update"
BEFORE UPDATE ON "olympus_evidence_bundle_amendments"
BEGIN
  SELECT RAISE(ABORT, 'olympus_evidence_bundle_amendments is append-only; corrections must INSERT a superseding row');
END;

-- olympus_forecast_amendments: append-only via reject_olympus_forecast_registry_mutation in Postgres.
CREATE TRIGGER IF NOT EXISTS "olympus_forecast_amendments_append_only_delete"
BEFORE DELETE ON "olympus_forecast_amendments"
BEGIN
  SELECT RAISE(ABORT, 'olympus_forecast_amendments is append-only; corrections must INSERT a superseding row');
END;
CREATE TRIGGER IF NOT EXISTS "olympus_forecast_amendments_append_only_update"
BEFORE UPDATE ON "olympus_forecast_amendments"
BEGIN
  SELECT RAISE(ABORT, 'olympus_forecast_amendments is append-only; corrections must INSERT a superseding row');
END;

-- olympus_forecast_assessments: append-only via reject_olympus_forecast_registry_mutation in Postgres.
CREATE TRIGGER IF NOT EXISTS "olympus_forecast_assessments_append_only_delete"
BEFORE DELETE ON "olympus_forecast_assessments"
BEGIN
  SELECT RAISE(ABORT, 'olympus_forecast_assessments is append-only; corrections must INSERT a superseding row');
END;
CREATE TRIGGER IF NOT EXISTS "olympus_forecast_assessments_append_only_update"
BEFORE UPDATE ON "olympus_forecast_assessments"
BEGIN
  SELECT RAISE(ABORT, 'olympus_forecast_assessments is append-only; corrections must INSERT a superseding row');
END;

-- olympus_forecast_calibrations: append-only via reject_olympus_forecast_calibration_mutation in Postgres.
CREATE TRIGGER IF NOT EXISTS "olympus_forecast_calibrations_append_only_delete"
BEFORE DELETE ON "olympus_forecast_calibrations"
BEGIN
  SELECT RAISE(ABORT, 'olympus_forecast_calibrations is append-only; corrections must INSERT a superseding row');
END;
CREATE TRIGGER IF NOT EXISTS "olympus_forecast_calibrations_append_only_update"
BEFORE UPDATE ON "olympus_forecast_calibrations"
BEGIN
  SELECT RAISE(ABORT, 'olympus_forecast_calibrations is append-only; corrections must INSERT a superseding row');
END;

-- olympus_forecast_outcomes: append-only via reject_olympus_forecast_calibration_mutation in Postgres.
CREATE TRIGGER IF NOT EXISTS "olympus_forecast_outcomes_append_only_delete"
BEFORE DELETE ON "olympus_forecast_outcomes"
BEGIN
  SELECT RAISE(ABORT, 'olympus_forecast_outcomes is append-only; corrections must INSERT a superseding row');
END;
CREATE TRIGGER IF NOT EXISTS "olympus_forecast_outcomes_append_only_update"
BEFORE UPDATE ON "olympus_forecast_outcomes"
BEGIN
  SELECT RAISE(ABORT, 'olympus_forecast_outcomes is append-only; corrections must INSERT a superseding row');
END;

-- olympus_gate_criteria_versions: append-only via reject_olympus_policy_replay_mutation in Postgres.
CREATE TRIGGER IF NOT EXISTS "olympus_gate_criteria_versions_append_only_delete"
BEFORE DELETE ON "olympus_gate_criteria_versions"
BEGIN
  SELECT RAISE(ABORT, 'olympus_gate_criteria_versions is append-only; corrections must INSERT a superseding row');
END;
CREATE TRIGGER IF NOT EXISTS "olympus_gate_criteria_versions_append_only_update"
BEFORE UPDATE ON "olympus_gate_criteria_versions"
BEGIN
  SELECT RAISE(ABORT, 'olympus_gate_criteria_versions is append-only; corrections must INSERT a superseding row');
END;

-- olympus_gate_evaluations: append-only via reject_olympus_policy_replay_mutation in Postgres.
CREATE TRIGGER IF NOT EXISTS "olympus_gate_evaluations_append_only_delete"
BEFORE DELETE ON "olympus_gate_evaluations"
BEGIN
  SELECT RAISE(ABORT, 'olympus_gate_evaluations is append-only; corrections must INSERT a superseding row');
END;
CREATE TRIGGER IF NOT EXISTS "olympus_gate_evaluations_append_only_update"
BEFORE UPDATE ON "olympus_gate_evaluations"
BEGIN
  SELECT RAISE(ABORT, 'olympus_gate_evaluations is append-only; corrections must INSERT a superseding row');
END;

-- olympus_h8_risk_run_refs: append-only via reject_olympus_risk_policy_snapshot_mutation in Postgres.
CREATE TRIGGER IF NOT EXISTS "olympus_h8_risk_run_refs_append_only_delete"
BEFORE DELETE ON "olympus_h8_risk_run_refs"
BEGIN
  SELECT RAISE(ABORT, 'olympus_h8_risk_run_refs is append-only; corrections must INSERT a superseding row');
END;
CREATE TRIGGER IF NOT EXISTS "olympus_h8_risk_run_refs_append_only_update"
BEFORE UPDATE ON "olympus_h8_risk_run_refs"
BEGIN
  SELECT RAISE(ABORT, 'olympus_h8_risk_run_refs is append-only; corrections must INSERT a superseding row');
END;

-- olympus_liquidity_snapshots: append-only via reject_olympus_cost_liquidity_mutation in Postgres.
CREATE TRIGGER IF NOT EXISTS "olympus_liquidity_snapshots_append_only_delete"
BEFORE DELETE ON "olympus_liquidity_snapshots"
BEGIN
  SELECT RAISE(ABORT, 'olympus_liquidity_snapshots is append-only; corrections must INSERT a superseding row');
END;
CREATE TRIGGER IF NOT EXISTS "olympus_liquidity_snapshots_append_only_update"
BEFORE UPDATE ON "olympus_liquidity_snapshots"
BEGIN
  SELECT RAISE(ABORT, 'olympus_liquidity_snapshots is append-only; corrections must INSERT a superseding row');
END;

-- olympus_missing_fact_requests: append-only via reject_olympus_evidence_bundle_mutation in Postgres.
CREATE TRIGGER IF NOT EXISTS "olympus_missing_fact_requests_append_only_delete"
BEFORE DELETE ON "olympus_missing_fact_requests"
BEGIN
  SELECT RAISE(ABORT, 'olympus_missing_fact_requests is append-only; corrections must INSERT a superseding row');
END;
CREATE TRIGGER IF NOT EXISTS "olympus_missing_fact_requests_append_only_update"
BEFORE UPDATE ON "olympus_missing_fact_requests"
BEGIN
  SELECT RAISE(ABORT, 'olympus_missing_fact_requests is append-only; corrections must INSERT a superseding row');
END;

-- olympus_node_runs: append-only via reject_olympus_provider_telemetry_mutation in Postgres.
CREATE TRIGGER IF NOT EXISTS "olympus_node_runs_append_only_delete"
BEFORE DELETE ON "olympus_node_runs"
BEGIN
  SELECT RAISE(ABORT, 'olympus_node_runs is append-only; corrections must INSERT a superseding row');
END;
CREATE TRIGGER IF NOT EXISTS "olympus_node_runs_append_only_update"
BEFORE UPDATE ON "olympus_node_runs"
BEGIN
  SELECT RAISE(ABORT, 'olympus_node_runs is append-only; corrections must INSERT a superseding row');
END;

-- olympus_outcome_episodes: append-only via reject_olympus_outcome_learning_mutation in Postgres.
CREATE TRIGGER IF NOT EXISTS "olympus_outcome_episodes_append_only_delete"
BEFORE DELETE ON "olympus_outcome_episodes"
BEGIN
  SELECT RAISE(ABORT, 'olympus_outcome_episodes is append-only; corrections must INSERT a superseding row');
END;
CREATE TRIGGER IF NOT EXISTS "olympus_outcome_episodes_append_only_update"
BEFORE UPDATE ON "olympus_outcome_episodes"
BEGIN
  SELECT RAISE(ABORT, 'olympus_outcome_episodes is append-only; corrections must INSERT a superseding row');
END;

-- olympus_outcome_lesson_versions: append-only via reject_olympus_outcome_learning_mutation in Postgres.
CREATE TRIGGER IF NOT EXISTS "olympus_outcome_lesson_versions_append_only_delete"
BEFORE DELETE ON "olympus_outcome_lesson_versions"
BEGIN
  SELECT RAISE(ABORT, 'olympus_outcome_lesson_versions is append-only; corrections must INSERT a superseding row');
END;
CREATE TRIGGER IF NOT EXISTS "olympus_outcome_lesson_versions_append_only_update"
BEFORE UPDATE ON "olympus_outcome_lesson_versions"
BEGIN
  SELECT RAISE(ABORT, 'olympus_outcome_lesson_versions is append-only; corrections must INSERT a superseding row');
END;

-- olympus_policy_comparison_reports: append-only via reject_olympus_policy_replay_mutation in Postgres.
CREATE TRIGGER IF NOT EXISTS "olympus_policy_comparison_reports_append_only_delete"
BEFORE DELETE ON "olympus_policy_comparison_reports"
BEGIN
  SELECT RAISE(ABORT, 'olympus_policy_comparison_reports is append-only; corrections must INSERT a superseding row');
END;
CREATE TRIGGER IF NOT EXISTS "olympus_policy_comparison_reports_append_only_update"
BEFORE UPDATE ON "olympus_policy_comparison_reports"
BEGIN
  SELECT RAISE(ABORT, 'olympus_policy_comparison_reports is append-only; corrections must INSERT a superseding row');
END;

-- olympus_policy_governance_decisions: append-only via reject_olympus_policy_replay_mutation in Postgres.
CREATE TRIGGER IF NOT EXISTS "olympus_policy_governance_decisions_append_only_delete"
BEFORE DELETE ON "olympus_policy_governance_decisions"
BEGIN
  SELECT RAISE(ABORT, 'olympus_policy_governance_decisions is append-only; corrections must INSERT a superseding row');
END;
CREATE TRIGGER IF NOT EXISTS "olympus_policy_governance_decisions_append_only_update"
BEFORE UPDATE ON "olympus_policy_governance_decisions"
BEGIN
  SELECT RAISE(ABORT, 'olympus_policy_governance_decisions is append-only; corrections must INSERT a superseding row');
END;

-- olympus_pretrade_risk_reports: append-only via reject_olympus_pretrade_risk_report_mutation in Postgres.
CREATE TRIGGER IF NOT EXISTS "olympus_pretrade_risk_reports_append_only_delete"
BEFORE DELETE ON "olympus_pretrade_risk_reports"
BEGIN
  SELECT RAISE(ABORT, 'olympus_pretrade_risk_reports is append-only; corrections must INSERT a superseding row');
END;
CREATE TRIGGER IF NOT EXISTS "olympus_pretrade_risk_reports_append_only_update"
BEFORE UPDATE ON "olympus_pretrade_risk_reports"
BEGIN
  SELECT RAISE(ABORT, 'olympus_pretrade_risk_reports is append-only; corrections must INSERT a superseding row');
END;

-- olympus_profile_config: append-only via reject_olympus_profile_config_mutation in Postgres.
CREATE TRIGGER IF NOT EXISTS "olympus_profile_config_append_only_delete"
BEFORE DELETE ON "olympus_profile_config"
BEGIN
  SELECT RAISE(ABORT, 'olympus_profile_config is append-only; corrections must INSERT a superseding row');
END;
CREATE TRIGGER IF NOT EXISTS "olympus_profile_config_append_only_update"
BEFORE UPDATE ON "olympus_profile_config"
BEGIN
  SELECT RAISE(ABORT, 'olympus_profile_config is append-only; corrections must INSERT a superseding row');
END;

-- olympus_provider_attempts: append-only via reject_olympus_provider_telemetry_mutation in Postgres.
CREATE TRIGGER IF NOT EXISTS "olympus_provider_attempts_append_only_delete"
BEFORE DELETE ON "olympus_provider_attempts"
BEGIN
  SELECT RAISE(ABORT, 'olympus_provider_attempts is append-only; corrections must INSERT a superseding row');
END;
CREATE TRIGGER IF NOT EXISTS "olympus_provider_attempts_append_only_update"
BEFORE UPDATE ON "olympus_provider_attempts"
BEGIN
  SELECT RAISE(ABORT, 'olympus_provider_attempts is append-only; corrections must INSERT a superseding row');
END;

-- olympus_provider_calls: append-only via reject_olympus_provider_telemetry_mutation in Postgres.
CREATE TRIGGER IF NOT EXISTS "olympus_provider_calls_append_only_delete"
BEFORE DELETE ON "olympus_provider_calls"
BEGIN
  SELECT RAISE(ABORT, 'olympus_provider_calls is append-only; corrections must INSERT a superseding row');
END;
CREATE TRIGGER IF NOT EXISTS "olympus_provider_calls_append_only_update"
BEFORE UPDATE ON "olympus_provider_calls"
BEGIN
  SELECT RAISE(ABORT, 'olympus_provider_calls is append-only; corrections must INSERT a superseding row');
END;

-- olympus_replay_arm_results: append-only via reject_olympus_policy_replay_mutation in Postgres.
CREATE TRIGGER IF NOT EXISTS "olympus_replay_arm_results_append_only_delete"
BEFORE DELETE ON "olympus_replay_arm_results"
BEGIN
  SELECT RAISE(ABORT, 'olympus_replay_arm_results is append-only; corrections must INSERT a superseding row');
END;
CREATE TRIGGER IF NOT EXISTS "olympus_replay_arm_results_append_only_update"
BEFORE UPDATE ON "olympus_replay_arm_results"
BEGIN
  SELECT RAISE(ABORT, 'olympus_replay_arm_results is append-only; corrections must INSERT a superseding row');
END;

-- olympus_replay_input_manifests: append-only via reject_olympus_policy_replay_mutation in Postgres.
CREATE TRIGGER IF NOT EXISTS "olympus_replay_input_manifests_append_only_delete"
BEFORE DELETE ON "olympus_replay_input_manifests"
BEGIN
  SELECT RAISE(ABORT, 'olympus_replay_input_manifests is append-only; corrections must INSERT a superseding row');
END;
CREATE TRIGGER IF NOT EXISTS "olympus_replay_input_manifests_append_only_update"
BEFORE UPDATE ON "olympus_replay_input_manifests"
BEGIN
  SELECT RAISE(ABORT, 'olympus_replay_input_manifests is append-only; corrections must INSERT a superseding row');
END;

-- olympus_replay_pairs: append-only via reject_olympus_policy_replay_mutation in Postgres.
CREATE TRIGGER IF NOT EXISTS "olympus_replay_pairs_append_only_delete"
BEFORE DELETE ON "olympus_replay_pairs"
BEGIN
  SELECT RAISE(ABORT, 'olympus_replay_pairs is append-only; corrections must INSERT a superseding row');
END;
CREATE TRIGGER IF NOT EXISTS "olympus_replay_pairs_append_only_update"
BEFORE UPDATE ON "olympus_replay_pairs"
BEGIN
  SELECT RAISE(ABORT, 'olympus_replay_pairs is append-only; corrections must INSERT a superseding row');
END;

-- olympus_replay_run_events: append-only via reject_olympus_policy_replay_mutation in Postgres.
CREATE TRIGGER IF NOT EXISTS "olympus_replay_run_events_append_only_delete"
BEFORE DELETE ON "olympus_replay_run_events"
BEGIN
  SELECT RAISE(ABORT, 'olympus_replay_run_events is append-only; corrections must INSERT a superseding row');
END;
CREATE TRIGGER IF NOT EXISTS "olympus_replay_run_events_append_only_update"
BEFORE UPDATE ON "olympus_replay_run_events"
BEGIN
  SELECT RAISE(ABORT, 'olympus_replay_run_events is append-only; corrections must INSERT a superseding row');
END;

-- olympus_research_belief_versions: append-only via reject_olympus_research_state_mutation in Postgres.
CREATE TRIGGER IF NOT EXISTS "olympus_research_belief_versions_append_only_delete"
BEFORE DELETE ON "olympus_research_belief_versions"
BEGIN
  SELECT RAISE(ABORT, 'olympus_research_belief_versions is append-only; corrections must INSERT a superseding row');
END;
CREATE TRIGGER IF NOT EXISTS "olympus_research_belief_versions_append_only_update"
BEFORE UPDATE ON "olympus_research_belief_versions"
BEGIN
  SELECT RAISE(ABORT, 'olympus_research_belief_versions is append-only; corrections must INSERT a superseding row');
END;

-- olympus_research_corpus: append-only via reject_olympus_research_corpus_mutation in Postgres.
CREATE TRIGGER IF NOT EXISTS "olympus_research_corpus_append_only_delete"
BEFORE DELETE ON "olympus_research_corpus"
BEGIN
  SELECT RAISE(ABORT, 'olympus_research_corpus is append-only; corrections must INSERT a superseding row');
END;
CREATE TRIGGER IF NOT EXISTS "olympus_research_corpus_append_only_update"
BEFORE UPDATE ON "olympus_research_corpus"
BEGIN
  SELECT RAISE(ABORT, 'olympus_research_corpus is append-only; corrections must INSERT a superseding row');
END;

-- olympus_research_evidence: append-only via reject_olympus_research_state_mutation in Postgres.
CREATE TRIGGER IF NOT EXISTS "olympus_research_evidence_append_only_delete"
BEFORE DELETE ON "olympus_research_evidence"
BEGIN
  SELECT RAISE(ABORT, 'olympus_research_evidence is append-only; corrections must INSERT a superseding row');
END;
CREATE TRIGGER IF NOT EXISTS "olympus_research_evidence_append_only_update"
BEFORE UPDATE ON "olympus_research_evidence"
BEGIN
  SELECT RAISE(ABORT, 'olympus_research_evidence is append-only; corrections must INSERT a superseding row');
END;

-- olympus_research_expected_event_versions: append-only via reject_olympus_research_state_mutation in Postgres.
CREATE TRIGGER IF NOT EXISTS "olympus_research_expected_event_versions_append_only_delete"
BEFORE DELETE ON "olympus_research_expected_event_versions"
BEGIN
  SELECT RAISE(ABORT, 'olympus_research_expected_event_versions is append-only; corrections must INSERT a superseding row');
END;
CREATE TRIGGER IF NOT EXISTS "olympus_research_expected_event_versions_append_only_update"
BEFORE UPDATE ON "olympus_research_expected_event_versions"
BEGIN
  SELECT RAISE(ABORT, 'olympus_research_expected_event_versions is append-only; corrections must INSERT a superseding row');
END;

-- olympus_research_legacy_refs: append-only via reject_olympus_research_state_mutation in Postgres.
CREATE TRIGGER IF NOT EXISTS "olympus_research_legacy_refs_append_only_delete"
BEFORE DELETE ON "olympus_research_legacy_refs"
BEGIN
  SELECT RAISE(ABORT, 'olympus_research_legacy_refs is append-only; corrections must INSERT a superseding row');
END;
CREATE TRIGGER IF NOT EXISTS "olympus_research_legacy_refs_append_only_update"
BEFORE UPDATE ON "olympus_research_legacy_refs"
BEGIN
  SELECT RAISE(ABORT, 'olympus_research_legacy_refs is append-only; corrections must INSERT a superseding row');
END;

-- olympus_research_patches: append-only via reject_olympus_research_state_mutation in Postgres.
CREATE TRIGGER IF NOT EXISTS "olympus_research_patches_append_only_delete"
BEFORE DELETE ON "olympus_research_patches"
BEGIN
  SELECT RAISE(ABORT, 'olympus_research_patches is append-only; corrections must INSERT a superseding row');
END;
CREATE TRIGGER IF NOT EXISTS "olympus_research_patches_append_only_update"
BEFORE UPDATE ON "olympus_research_patches"
BEGIN
  SELECT RAISE(ABORT, 'olympus_research_patches is append-only; corrections must INSERT a superseding row');
END;

-- olympus_research_state_pins: append-only via reject_olympus_research_state_mutation in Postgres.
CREATE TRIGGER IF NOT EXISTS "olympus_research_state_pins_append_only_delete"
BEFORE DELETE ON "olympus_research_state_pins"
BEGIN
  SELECT RAISE(ABORT, 'olympus_research_state_pins is append-only; corrections must INSERT a superseding row');
END;
CREATE TRIGGER IF NOT EXISTS "olympus_research_state_pins_append_only_update"
BEFORE UPDATE ON "olympus_research_state_pins"
BEGIN
  SELECT RAISE(ABORT, 'olympus_research_state_pins is append-only; corrections must INSERT a superseding row');
END;

-- olympus_research_state_versions: append-only via reject_olympus_research_state_mutation in Postgres.
CREATE TRIGGER IF NOT EXISTS "olympus_research_state_versions_append_only_delete"
BEFORE DELETE ON "olympus_research_state_versions"
BEGIN
  SELECT RAISE(ABORT, 'olympus_research_state_versions is append-only; corrections must INSERT a superseding row');
END;
CREATE TRIGGER IF NOT EXISTS "olympus_research_state_versions_append_only_update"
BEFORE UPDATE ON "olympus_research_state_versions"
BEGIN
  SELECT RAISE(ABORT, 'olympus_research_state_versions is append-only; corrections must INSERT a superseding row');
END;

-- olympus_risk_policies: append-only via reject_olympus_risk_policy_snapshot_mutation in Postgres.
CREATE TRIGGER IF NOT EXISTS "olympus_risk_policies_append_only_delete"
BEFORE DELETE ON "olympus_risk_policies"
BEGIN
  SELECT RAISE(ABORT, 'olympus_risk_policies is append-only; corrections must INSERT a superseding row');
END;
CREATE TRIGGER IF NOT EXISTS "olympus_risk_policies_append_only_update"
BEFORE UPDATE ON "olympus_risk_policies"
BEGIN
  SELECT RAISE(ABORT, 'olympus_risk_policies is append-only; corrections must INSERT a superseding row');
END;

-- olympus_ticker_evidence_bundles: append-only via reject_olympus_evidence_bundle_mutation in Postgres.
CREATE TRIGGER IF NOT EXISTS "olympus_ticker_evidence_bundles_append_only_delete"
BEFORE DELETE ON "olympus_ticker_evidence_bundles"
BEGIN
  SELECT RAISE(ABORT, 'olympus_ticker_evidence_bundles is append-only; corrections must INSERT a superseding row');
END;
CREATE TRIGGER IF NOT EXISTS "olympus_ticker_evidence_bundles_append_only_update"
BEFORE UPDATE ON "olympus_ticker_evidence_bundles"
BEGIN
  SELECT RAISE(ABORT, 'olympus_ticker_evidence_bundles is append-only; corrections must INSERT a superseding row');
END;

-- portfolio_ledger_approved_targets: append-only via reject_portfolio_ledger_mutation in Postgres.
CREATE TRIGGER IF NOT EXISTS "portfolio_ledger_approved_targets_append_only_delete"
BEFORE DELETE ON "portfolio_ledger_approved_targets"
BEGIN
  SELECT RAISE(ABORT, 'portfolio_ledger_approved_targets is append-only; corrections must INSERT a superseding row');
END;
CREATE TRIGGER IF NOT EXISTS "portfolio_ledger_approved_targets_append_only_update"
BEFORE UPDATE ON "portfolio_ledger_approved_targets"
BEGIN
  SELECT RAISE(ABORT, 'portfolio_ledger_approved_targets is append-only; corrections must INSERT a superseding row');
END;

-- portfolio_ledger_commits: append-only via reject_portfolio_ledger_mutation in Postgres.
CREATE TRIGGER IF NOT EXISTS "portfolio_ledger_commits_append_only_delete"
BEFORE DELETE ON "portfolio_ledger_commits"
BEGIN
  SELECT RAISE(ABORT, 'portfolio_ledger_commits is append-only; corrections must INSERT a superseding row');
END;
CREATE TRIGGER IF NOT EXISTS "portfolio_ledger_commits_append_only_update"
BEFORE UPDATE ON "portfolio_ledger_commits"
BEGIN
  SELECT RAISE(ABORT, 'portfolio_ledger_commits is append-only; corrections must INSERT a superseding row');
END;

-- portfolio_ledger_decision_intents: append-only via reject_portfolio_ledger_mutation in Postgres.
CREATE TRIGGER IF NOT EXISTS "portfolio_ledger_decision_intents_append_only_delete"
BEFORE DELETE ON "portfolio_ledger_decision_intents"
BEGIN
  SELECT RAISE(ABORT, 'portfolio_ledger_decision_intents is append-only; corrections must INSERT a superseding row');
END;
CREATE TRIGGER IF NOT EXISTS "portfolio_ledger_decision_intents_append_only_update"
BEFORE UPDATE ON "portfolio_ledger_decision_intents"
BEGIN
  SELECT RAISE(ABORT, 'portfolio_ledger_decision_intents is append-only; corrections must INSERT a superseding row');
END;

-- portfolio_ledger_holding_lots: append-only via reject_portfolio_ledger_mutation in Postgres.
CREATE TRIGGER IF NOT EXISTS "portfolio_ledger_holding_lots_append_only_delete"
BEFORE DELETE ON "portfolio_ledger_holding_lots"
BEGIN
  SELECT RAISE(ABORT, 'portfolio_ledger_holding_lots is append-only; corrections must INSERT a superseding row');
END;
CREATE TRIGGER IF NOT EXISTS "portfolio_ledger_holding_lots_append_only_update"
BEFORE UPDATE ON "portfolio_ledger_holding_lots"
BEGIN
  SELECT RAISE(ABORT, 'portfolio_ledger_holding_lots is append-only; corrections must INSERT a superseding row');
END;

-- portfolio_ledger_order_intents: append-only via reject_portfolio_ledger_mutation in Postgres.
CREATE TRIGGER IF NOT EXISTS "portfolio_ledger_order_intents_append_only_delete"
BEFORE DELETE ON "portfolio_ledger_order_intents"
BEGIN
  SELECT RAISE(ABORT, 'portfolio_ledger_order_intents is append-only; corrections must INSERT a superseding row');
END;
CREATE TRIGGER IF NOT EXISTS "portfolio_ledger_order_intents_append_only_update"
BEFORE UPDATE ON "portfolio_ledger_order_intents"
BEGIN
  SELECT RAISE(ABORT, 'portfolio_ledger_order_intents is append-only; corrections must INSERT a superseding row');
END;

-- portfolio_ledger_paper_executions: append-only via reject_portfolio_ledger_mutation in Postgres.
CREATE TRIGGER IF NOT EXISTS "portfolio_ledger_paper_executions_append_only_delete"
BEFORE DELETE ON "portfolio_ledger_paper_executions"
BEGIN
  SELECT RAISE(ABORT, 'portfolio_ledger_paper_executions is append-only; corrections must INSERT a superseding row');
END;
CREATE TRIGGER IF NOT EXISTS "portfolio_ledger_paper_executions_append_only_update"
BEFORE UPDATE ON "portfolio_ledger_paper_executions"
BEGIN
  SELECT RAISE(ABORT, 'portfolio_ledger_paper_executions is append-only; corrections must INSERT a superseding row');
END;

-- portfolio_ledger_requested_targets: append-only via reject_portfolio_ledger_mutation in Postgres.
CREATE TRIGGER IF NOT EXISTS "portfolio_ledger_requested_targets_append_only_delete"
BEFORE DELETE ON "portfolio_ledger_requested_targets"
BEGIN
  SELECT RAISE(ABORT, 'portfolio_ledger_requested_targets is append-only; corrections must INSERT a superseding row');
END;
CREATE TRIGGER IF NOT EXISTS "portfolio_ledger_requested_targets_append_only_update"
BEFORE UPDATE ON "portfolio_ledger_requested_targets"
BEGIN
  SELECT RAISE(ABORT, 'portfolio_ledger_requested_targets is append-only; corrections must INSERT a superseding row');
END;

-- portfolio_ledger_target_adjustments: append-only via reject_portfolio_ledger_mutation in Postgres.
CREATE TRIGGER IF NOT EXISTS "portfolio_ledger_target_adjustments_append_only_delete"
BEFORE DELETE ON "portfolio_ledger_target_adjustments"
BEGIN
  SELECT RAISE(ABORT, 'portfolio_ledger_target_adjustments is append-only; corrections must INSERT a superseding row');
END;
CREATE TRIGGER IF NOT EXISTS "portfolio_ledger_target_adjustments_append_only_update"
BEFORE UPDATE ON "portfolio_ledger_target_adjustments"
BEGIN
  SELECT RAISE(ABORT, 'portfolio_ledger_target_adjustments is append-only; corrections must INSERT a superseding row');
END;

-- workspace_provider_credentials: append-only via reject_workspace_provider_credential_mutation in Postgres.
CREATE TRIGGER IF NOT EXISTS "workspace_provider_credentials_append_only_update"
BEFORE UPDATE ON "workspace_provider_credentials"
BEGIN
  SELECT RAISE(ABORT, 'workspace_provider_credentials is append-only; corrections must INSERT a superseding row');
END;

COMMIT;

-- ----------------------------------------------------------------------
-- Worker-side obligations. NOT enforced by this file: SQLite has no
-- TRUNCATE and no statement-level trigger. The Worker data API must
-- refuse these operations in application code. See DIG-2894 / DIG-2892.
-- ----------------------------------------------------------------------
--   TRUNCATE  ON broker_connections                         (Postgres reject_broker_connection_credential_mutation, 099_broker_connections.sql)
--   TRUNCATE  ON broker_executions                          (Postgres reject_broker_mirror_mutation, 102_kairos_broker_mirror.sql)
--   TRUNCATE  ON broker_orders                              (Postgres reject_broker_mirror_mutation, 102_kairos_broker_mirror.sql)
--   TRUNCATE  ON broker_position_snapshots                  (Postgres reject_broker_mirror_mutation, 102_kairos_broker_mirror.sql)
--   TRUNCATE  ON notification_log                           (Postgres reject_notification_log_mutation, 103_notification_prefs.sql)
--   TRUNCATE  ON notification_log                           (Postgres reject_notification_log_mutation, 106_notification_prefs_align_canonical.sql)
--   TRUNCATE  ON olympus_accounting_contributions           (Postgres reject_olympus_accounting_mutation, 072_olympus_period_accounting.sql)
--   TRUNCATE  ON olympus_accounting_holdings                (Postgres reject_olympus_accounting_mutation, 072_olympus_period_accounting.sql)
--   TRUNCATE  ON olympus_accounting_periods                 (Postgres reject_olympus_accounting_mutation, 072_olympus_period_accounting.sql)
--   TRUNCATE  ON olympus_action_cost_estimates              (Postgres reject_olympus_cost_liquidity_mutation, 082_olympus_cost_liquidity.sql)
--   TRUNCATE  ON olympus_action_cost_outcomes               (Postgres reject_olympus_cost_liquidity_mutation, 082_olympus_cost_liquidity.sql)
--   TRUNCATE  ON olympus_attention_context_manifests        (Postgres reject_olympus_attention_context_mutation, 092_olympus_attention_context.sql)
--   TRUNCATE  ON olympus_attention_decision_attempts        (Postgres reject_olympus_attention_context_mutation, 092_olympus_attention_context.sql)
--   TRUNCATE  ON olympus_attention_decisions                (Postgres reject_olympus_attention_context_mutation, 092_olympus_attention_context.sql)
--   TRUNCATE  ON olympus_attention_plans                    (Postgres reject_olympus_attention_context_mutation, 092_olympus_attention_context.sql)
--   TRUNCATE  ON olympus_attention_policy_evaluations       (Postgres reject_olympus_attention_context_mutation, 092_olympus_attention_context.sql)
--   TRUNCATE  ON olympus_calibrated_forecasts               (Postgres reject_olympus_forecast_calibration_mutation, 080_olympus_forecast_calibration.sql)
--   TRUNCATE  ON olympus_component_attribution_reports      (Postgres reject_olympus_outcome_learning_mutation, 093_olympus_outcome_learning.sql)
--   TRUNCATE  ON olympus_covariance_snapshots               (Postgres reject_olympus_risk_policy_snapshot_mutation, 081_olympus_risk_policy_snapshots.sql)
--   TRUNCATE  ON olympus_evidence_bundle_amendments         (Postgres reject_olympus_evidence_bundle_mutation, 090_olympus_evidence_bundles.sql)
--   TRUNCATE  ON olympus_forecast_amendments                (Postgres reject_olympus_forecast_registry_mutation, 079_olympus_forecast_registry.sql)
--   TRUNCATE  ON olympus_forecast_assessments               (Postgres reject_olympus_forecast_registry_mutation, 079_olympus_forecast_registry.sql)
--   TRUNCATE  ON olympus_forecast_calibrations              (Postgres reject_olympus_forecast_calibration_mutation, 080_olympus_forecast_calibration.sql)
--   TRUNCATE  ON olympus_forecast_outcomes                  (Postgres reject_olympus_forecast_calibration_mutation, 080_olympus_forecast_calibration.sql)
--   TRUNCATE  ON olympus_gate_criteria_versions             (Postgres reject_olympus_policy_replay_mutation, 094_olympus_policy_replay.sql)
--   TRUNCATE  ON olympus_gate_evaluations                   (Postgres reject_olympus_policy_replay_mutation, 094_olympus_policy_replay.sql)
--   TRUNCATE  ON olympus_h8_risk_run_refs                   (Postgres reject_olympus_risk_policy_snapshot_mutation, 081_olympus_risk_policy_snapshots.sql)
--   TRUNCATE  ON olympus_liquidity_snapshots                (Postgres reject_olympus_cost_liquidity_mutation, 082_olympus_cost_liquidity.sql)
--   TRUNCATE  ON olympus_missing_fact_requests              (Postgres reject_olympus_evidence_bundle_mutation, 090_olympus_evidence_bundles.sql)
--   TRUNCATE  ON olympus_node_runs                          (Postgres reject_olympus_provider_telemetry_mutation, 067_olympus_provider_telemetry.sql)
--   TRUNCATE  ON olympus_outcome_episodes                   (Postgres reject_olympus_outcome_learning_mutation, 093_olympus_outcome_learning.sql)
--   TRUNCATE  ON olympus_outcome_lesson_versions            (Postgres reject_olympus_outcome_learning_mutation, 093_olympus_outcome_learning.sql)
--   TRUNCATE  ON olympus_policy_comparison_reports          (Postgres reject_olympus_policy_replay_mutation, 094_olympus_policy_replay.sql)
--   TRUNCATE  ON olympus_policy_governance_decisions        (Postgres reject_olympus_policy_replay_mutation, 094_olympus_policy_replay.sql)
--   TRUNCATE  ON olympus_pretrade_risk_reports              (Postgres reject_olympus_pretrade_risk_report_mutation, 083_olympus_pretrade_risk_reports.sql)
--   TRUNCATE  ON olympus_profile_config                     (Postgres reject_olympus_profile_config_mutation, 075_olympus_profile_config.sql)
--   TRUNCATE  ON olympus_provider_attempts                  (Postgres reject_olympus_provider_telemetry_mutation, 067_olympus_provider_telemetry.sql)
--   TRUNCATE  ON olympus_provider_calls                     (Postgres reject_olympus_provider_telemetry_mutation, 067_olympus_provider_telemetry.sql)
--   TRUNCATE  ON olympus_replay_arm_results                 (Postgres reject_olympus_policy_replay_mutation, 094_olympus_policy_replay.sql)
--   TRUNCATE  ON olympus_replay_input_manifests             (Postgres reject_olympus_policy_replay_mutation, 094_olympus_policy_replay.sql)
--   TRUNCATE  ON olympus_replay_pairs                       (Postgres reject_olympus_policy_replay_mutation, 094_olympus_policy_replay.sql)
--   TRUNCATE  ON olympus_replay_run_events                  (Postgres reject_olympus_policy_replay_mutation, 094_olympus_policy_replay.sql)
--   TRUNCATE  ON olympus_research_belief_versions           (Postgres reject_olympus_research_state_mutation, 088_olympus_research_state.sql)
--   TRUNCATE  ON olympus_research_corpus                    (Postgres reject_olympus_research_corpus_mutation, 076_olympus_research_corpus.sql)
--   TRUNCATE  ON olympus_research_evidence                  (Postgres reject_olympus_research_state_mutation, 088_olympus_research_state.sql)
--   TRUNCATE  ON olympus_research_expected_event_versions   (Postgres reject_olympus_research_state_mutation, 088_olympus_research_state.sql)
--   TRUNCATE  ON olympus_research_legacy_refs               (Postgres reject_olympus_research_state_mutation, 088_olympus_research_state.sql)
--   TRUNCATE  ON olympus_research_patches                   (Postgres reject_olympus_research_state_mutation, 088_olympus_research_state.sql)
--   TRUNCATE  ON olympus_research_state_pins                (Postgres reject_olympus_research_state_mutation, 088_olympus_research_state.sql)
--   TRUNCATE  ON olympus_research_state_versions            (Postgres reject_olympus_research_state_mutation, 088_olympus_research_state.sql)
--   TRUNCATE  ON olympus_risk_policies                      (Postgres reject_olympus_risk_policy_snapshot_mutation, 081_olympus_risk_policy_snapshots.sql)
--   TRUNCATE  ON olympus_ticker_evidence_bundles            (Postgres reject_olympus_evidence_bundle_mutation, 090_olympus_evidence_bundles.sql)
--   TRUNCATE  ON portfolio_ledger_approved_targets          (Postgres reject_portfolio_ledger_mutation, 069_olympus_portfolio_ledger.sql)
--   TRUNCATE  ON portfolio_ledger_commits                   (Postgres reject_portfolio_ledger_mutation, 069_olympus_portfolio_ledger.sql)
--   TRUNCATE  ON portfolio_ledger_decision_intents          (Postgres reject_portfolio_ledger_mutation, 069_olympus_portfolio_ledger.sql)
--   TRUNCATE  ON portfolio_ledger_holding_lots              (Postgres reject_portfolio_ledger_mutation, 069_olympus_portfolio_ledger.sql)
--   TRUNCATE  ON portfolio_ledger_order_intents             (Postgres reject_portfolio_ledger_mutation, 069_olympus_portfolio_ledger.sql)
--   TRUNCATE  ON portfolio_ledger_paper_executions          (Postgres reject_portfolio_ledger_mutation, 069_olympus_portfolio_ledger.sql)
--   TRUNCATE  ON portfolio_ledger_requested_targets         (Postgres reject_portfolio_ledger_mutation, 069_olympus_portfolio_ledger.sql)
--   TRUNCATE  ON portfolio_ledger_target_adjustments        (Postgres reject_portfolio_ledger_mutation, 069_olympus_portfolio_ledger.sql)
--   TRUNCATE  ON workspace_provider_credentials             (Postgres reject_workspace_provider_credential_mutation, 104_workspace_provider_credentials.sql)
