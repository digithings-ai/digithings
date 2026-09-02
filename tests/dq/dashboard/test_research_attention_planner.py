"""WP13.1 — versioned research attention policy and deterministic routing (#2918)."""

from __future__ import annotations

from uuid import UUID

import pytest
import yaml
from digiquant.olympus.research_retrieval.planner import (
    AttentionDecision,
    AttentionFeatures,
    AttentionMode,
    AttentionPlan,
    AttentionReason,
    AttentionRolloutMode,
    AttentionTargetKind,
    H6DecisionFeatures,
    ResearchAttentionPolicy,
    apply_session_budget,
    attention_plan_id,
    default_research_policy_path,
    load_research_attention_policy,
    plan_research_attention,
    policy_content_hash,
    route_attention,
    sum_budget_estimates,
)
from pydantic import ValidationError

pytestmark = pytest.mark.unit

POLICY_PATH = default_research_policy_path()
RUN_ID = "run-wp131-test"
STATE_VERSION = UUID("aaaaaaaa-bbbb-4ccc-8ddd-eeeeeeeeeeee")


def _policy() -> ResearchAttentionPolicy:
    return load_research_attention_policy(POLICY_PATH)


def _ticker_features(**overrides: object) -> AttentionFeatures:
    h6_base: dict[str, object] = {
        "ticker": "AAPL",
        "roster_reason": "held",
        "held": True,
        "weight_pct": 1.0,
        "stance": "hold",
        "conviction_score": 1,
        "raw_uncertainty": "low",
    }
    h6_overrides = {k: v for k, v in overrides.items() if k in H6DecisionFeatures.model_fields}
    h6_base.update(h6_overrides)
    ticker = str(h6_base.get("ticker", "AAPL"))
    feature_overrides = {
        k: v for k, v in overrides.items() if k not in H6DecisionFeatures.model_fields
    }
    return AttentionFeatures(
        target_kind=AttentionTargetKind.TICKER,
        target_key=ticker,
        state_version_id=str(STATE_VERSION),
        has_prior=True,
        h6=H6DecisionFeatures.model_validate(h6_base),
        **feature_overrides,  # type: ignore[arg-type]
    )


def _artifact_features(**overrides: object) -> AttentionFeatures:
    base: dict[str, object] = {
        "target_kind": AttentionTargetKind.ARTIFACT,
        "target_key": "segment:macro",
        "state_version_id": str(STATE_VERSION),
        "has_prior": True,
    }
    base.update(overrides)
    return AttentionFeatures.model_validate(base)


class TestResearchAttentionPolicy:
    def test_default_policy_loads_with_content_hash(self) -> None:
        policy = _policy()
        assert policy.schema_version == 1
        assert policy.policy_version == "2026-08-26"
        assert len(policy.content_hash) == 64
        raw = yaml.safe_load(POLICY_PATH.read_text(encoding="utf-8"))
        assert policy.content_hash == policy_content_hash(raw)

    def test_policy_hash_changes_when_content_changes(self) -> None:
        raw = yaml.safe_load(POLICY_PATH.read_text(encoding="utf-8"))
        a = policy_content_hash(raw)
        mutated = dict(raw)
        mutated["session_budget"] = dict(raw["session_budget"])
        mutated["session_budget"]["max_provider_calls"] = 49
        b = policy_content_hash(mutated)
        assert a != b


class TestAttentionRouting:
    def test_five_modes_present(self) -> None:
        assert {m.value for m in AttentionMode} == {
            "carry",
            "metric_patch",
            "section_patch",
            "challenge",
            "deep_refresh",
        }

    def test_low_value_ticker_carries(self) -> None:
        decision = route_attention(_ticker_features(weight_pct=0.5, held=False), _policy())
        assert decision.mode is AttentionMode.CARRY
        assert decision.reason is AttentionReason.LOW_VALUE_CARRY
        assert decision.budget.provider_calls == 0

    def test_conflict_routes_to_challenge(self) -> None:
        decision = route_attention(
            _ticker_features(has_evidence_conflict=True, counter_evidence_count=2),
            _policy(),
        )
        assert decision.mode is AttentionMode.CHALLENGE
        assert decision.reason is AttentionReason.CONFLICT
        assert decision.budget.min_h6_rounds >= 2

    def test_structured_delta_routes_to_metric_patch(self) -> None:
        decision = route_attention(
            _artifact_features(has_structured_delta=True, has_prior=True, triage_mode="quiet"),
            _policy(),
        )
        assert decision.mode is AttentionMode.METRIC_PATCH
        assert decision.reason is AttentionReason.STRUCTURED_DELTA
        assert decision.budget.provider_calls == 0

    def test_triage_stale_routes_to_section_patch(self) -> None:
        decision = route_attention(
            _artifact_features(triage_mode="stale", has_prior=True),
            _policy(),
        )
        assert decision.mode is AttentionMode.SECTION_PATCH
        assert decision.reason is AttentionReason.TRIAGE_STALE

    def test_no_prior_routes_to_deep_refresh(self) -> None:
        decision = route_attention(_artifact_features(has_prior=False), _policy())
        assert decision.mode is AttentionMode.DEEP_REFRESH
        assert decision.reason is AttentionReason.NO_PRIOR

    def test_deterministic_tie_break_by_reason_priority(self) -> None:
        """Conflict beats decision_boundary when both signals fire."""
        features = _ticker_features(
            has_evidence_conflict=True,
            stance_changed=True,
            stance="buy",
            prior_stance="hold",
        )
        a = route_attention(features, _policy())
        b = route_attention(features, _policy())
        assert a == b
        assert a.reason is AttentionReason.CONFLICT

    def test_exploration_slot_reserved_under_budget_pressure(self) -> None:
        policy = _policy()
        many = [
            _ticker_features(ticker=f"LOW{i}", weight_pct=0.1, held=False, roster_reason="held")
            for i in range(20)
        ] + [
            _ticker_features(
                ticker=f"EXP{i}",
                roster_reason="technical",
                held=False,
                weight_pct=0.0,
                exploration_slot=True,
            )
            for i in range(3)
        ]
        plan = plan_research_attention(
            run_id=RUN_ID,
            state_version_id=STATE_VERSION,
            features=many,
            policy=policy,
            rollout_mode=AttentionRolloutMode.SHADOW,
        )
        exploration_decisions = [
            d
            for d in plan.decisions
            if d.features.exploration_slot and d.mode is not AttentionMode.CARRY
        ]
        assert len(exploration_decisions) >= policy.exploration.min_reserved_slots
        assert plan.total_budget.provider_calls <= policy.session_budget.max_provider_calls


class TestAttentionPlan:
    def test_identical_inputs_yield_identical_plan_and_totals(self) -> None:
        policy = _policy()
        features = [
            _ticker_features(ticker="MSFT", weight_pct=8.0),
            _artifact_features(target_key="theme:ai", triage_mode="stale"),
        ]
        a = plan_research_attention(
            run_id=RUN_ID,
            state_version_id=STATE_VERSION,
            features=features,
            policy=policy,
            rollout_mode=AttentionRolloutMode.SHADOW,
        )
        b = plan_research_attention(
            run_id=RUN_ID,
            state_version_id=STATE_VERSION,
            features=features,
            policy=policy,
            rollout_mode=AttentionRolloutMode.SHADOW,
        )
        assert a == b
        assert a.plan_id == b.plan_id
        assert a.total_budget == b.total_budget
        assert a.plan_id == attention_plan_id(
            run_id=RUN_ID,
            state_version_id=STATE_VERSION,
            policy_content_hash=policy.content_hash,
            target_keys=tuple(d.target_key for d in a.decisions),
        )

    def test_plan_survives_budget_trimming_that_drops_targets(self) -> None:
        policy = _policy()
        features = [
            _ticker_features(ticker=f"LOW{i}", weight_pct=0.1, held=False, roster_reason="held")
            for i in range(25)
        ] + [_artifact_features(target_key=f"theme:{i}", has_prior=False) for i in range(10)]
        plan = plan_research_attention(
            run_id=RUN_ID,
            state_version_id=STATE_VERSION,
            features=features,
            policy=policy,
            rollout_mode=AttentionRolloutMode.SHADOW,
        )
        assert plan.plan_id
        assert plan.total_budget.provider_calls <= policy.session_budget.max_provider_calls
        assert any(d.mode is not AttentionMode.DEEP_REFRESH for d in plan.decisions)

    def test_many_exploration_slots_respect_session_budget(self) -> None:
        policy = _policy()
        features = [
            _ticker_features(
                ticker=f"EXP{i}",
                roster_reason="technical",
                held=False,
                weight_pct=0.0,
                exploration_slot=True,
            )
            for i in range(20)
        ]
        plan = plan_research_attention(
            run_id=RUN_ID,
            state_version_id=STATE_VERSION,
            features=features,
            policy=policy,
            rollout_mode=AttentionRolloutMode.SHADOW,
        )
        assert plan.total_budget.provider_calls <= policy.session_budget.max_provider_calls
        reserved = [d for d in plan.decisions if d.exploration_reserved]
        assert len(reserved) == policy.exploration.min_reserved_slots

    def test_shadow_records_plan_without_actuation(self) -> None:
        plan = plan_research_attention(
            run_id=RUN_ID,
            state_version_id=STATE_VERSION,
            features=[_ticker_features()],
            policy=_policy(),
            rollout_mode=AttentionRolloutMode.SHADOW,
        )
        assert plan.rollout_mode is AttentionRolloutMode.SHADOW
        assert plan.actuated is False
        assert plan.decisions

    def test_off_mode_is_immediate_rollback(self) -> None:
        plan = plan_research_attention(
            run_id=RUN_ID,
            state_version_id=STATE_VERSION,
            features=[_ticker_features()],
            policy=_policy(),
            rollout_mode=AttentionRolloutMode.OFF,
        )
        assert plan.rollout_mode is AttentionRolloutMode.OFF
        assert plan.decisions == ()
        assert plan.total_budget.provider_calls == 0

    def test_enforce_sets_actuated_true(self) -> None:
        plan = plan_research_attention(
            run_id=RUN_ID,
            state_version_id=STATE_VERSION,
            features=[_ticker_features(has_evidence_conflict=True)],
            policy=_policy(),
            rollout_mode=AttentionRolloutMode.ENFORCE,
        )
        assert plan.actuated is True
        assert all(d.actuated for d in plan.decisions)

    def test_stable_reason_codes_on_decision(self) -> None:
        decision = route_attention(
            _ticker_features(invalidation_risk=True, has_evidence_conflict=True),
            _policy(),
        )
        assert decision.reason is AttentionReason.INVALIDATION_RISK
        assert AttentionReason.INVALIDATION_RISK in decision.reasons
        assert decision.reasons[0] is AttentionReason.INVALIDATION_RISK

    def test_budget_estimates_include_calls_searches_tokens(self) -> None:
        decision = route_attention(_ticker_features(has_evidence_conflict=True), _policy())
        assert decision.budget.provider_calls > 0
        assert decision.budget.searches >= 0
        assert decision.budget.uncached_tokens > 0

    def test_sum_budget_estimates(self) -> None:
        decisions = (
            route_attention(_ticker_features(ticker="A"), _policy()),
            route_attention(_ticker_features(ticker="B", has_evidence_conflict=True), _policy()),
        )
        total = sum_budget_estimates(decisions)
        assert total.provider_calls == sum(d.budget.provider_calls for d in decisions)


class TestSessionBudget:
    def test_apply_session_budget_never_strips_exploration_floor(self) -> None:
        policy = _policy()
        decisions = [
            AttentionDecision(
                target_key=f"EXP{i}",
                mode=AttentionMode.CHALLENGE,
                reason=AttentionReason.EXPLORATION,
                reasons=(AttentionReason.EXPLORATION,),
                features=_ticker_features(ticker=f"EXP{i}", exploration_slot=True),
                budget=policy.mode_budgets[AttentionMode.CHALLENGE],
                exploration_reserved=True,
                actuated=False,
            )
            for i in range(policy.exploration.min_reserved_slots)
        ] + [
            AttentionDecision(
                target_key=f"DEEP{i}",
                mode=AttentionMode.DEEP_REFRESH,
                reason=AttentionReason.NO_PRIOR,
                reasons=(AttentionReason.NO_PRIOR,),
                features=_artifact_features(target_key=f"theme:{i}", has_prior=False),
                budget=policy.mode_budgets[AttentionMode.DEEP_REFRESH],
                exploration_reserved=False,
                actuated=False,
            )
            for i in range(20)
        ]
        trimmed, total = apply_session_budget(decisions, policy)
        reserved = [d for d in trimmed if d.exploration_reserved]
        assert len(reserved) >= policy.exploration.min_reserved_slots
        assert all(d.mode is AttentionMode.CHALLENGE for d in reserved)
        assert total.provider_calls <= policy.session_budget.max_provider_calls


class TestValidation:
    def test_attention_plan_rejects_mismatched_policy_hash(self) -> None:
        policy = _policy()
        with pytest.raises(ValidationError):
            AttentionPlan(
                plan_id=attention_plan_id(
                    run_id=RUN_ID,
                    state_version_id=STATE_VERSION,
                    policy_content_hash="0" * 64,
                    target_keys=("AAPL",),
                ),
                run_id=RUN_ID,
                state_version_id=STATE_VERSION,
                policy_content_hash="f" * 64,
                rollout_mode=AttentionRolloutMode.SHADOW,
                actuated=False,
                decisions=(),
                total_budget=policy.mode_budgets[AttentionMode.CARRY],
                exploration_slots_reserved=0,
            )
