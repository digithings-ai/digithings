"""WP13.2 — append-only attention plan/decision/context/evaluation store (#2922)."""

from __future__ import annotations

from datetime import UTC, datetime, timedelta
from decimal import Decimal
from uuid import UUID, uuid4

import pytest
from digiquant.olympus.research_retrieval.planner import (
    AttentionContextManifest,
    AttentionDecisionReconciliation,
    AttentionMode,
    AttentionPolicyEvaluation,
    AttentionReason,
    AttentionRolloutMode,
    AttentionTargetKind,
    H6DecisionFeatures,
    PersistedAttentionPlan,
    attention_decision_id,
    default_research_policy_path,
    load_research_attention_policy,
    plan_research_attention,
)
from digiquant.olympus.research_retrieval.store import (
    ActualProviderAttemptUsage,
    AttentionStore,
    AttentionStoreConflict,
    AttentionStoreError,
    AttentionStoreMissingError,
)

pytestmark = pytest.mark.unit

_TS = datetime(2026, 8, 26, 14, 0, tzinfo=UTC)
_RUN = "run-wp132"
_ATTEMPT = "attempt-1"
_STATE = UUID("aaaaaaaa-bbbb-4ccc-8ddd-eeeeeeeeeeee")


def _ticker_features(ticker: str = "AAPL", **overrides: object):
    from digiquant.olympus.research_retrieval.planner import AttentionFeatures

    h6_base: dict[str, object] = {
        "ticker": ticker,
        "roster_reason": "held",
        "held": True,
        "weight_pct": 8.0,
        "stance": "hold",
        "conviction_score": 2,
        "raw_uncertainty": "low",
    }
    h6_overrides = {k: v for k, v in overrides.items() if k in H6DecisionFeatures.model_fields}
    h6_base.update(h6_overrides)
    feature_overrides = {
        k: v for k, v in overrides.items() if k not in H6DecisionFeatures.model_fields
    }
    return AttentionFeatures(
        target_kind=AttentionTargetKind.TICKER,
        target_key=ticker,
        state_version_id=str(_STATE),
        has_prior=True,
        h6=H6DecisionFeatures.model_validate(h6_base),
        **feature_overrides,  # type: ignore[arg-type]
    )


def _shadow_plan():
    policy = load_research_attention_policy(default_research_policy_path())
    return plan_research_attention(
        run_id=_RUN,
        state_version_id=_STATE,
        features=[_ticker_features(), _ticker_features(ticker="MSFT", weight_pct=0.5, held=False)],
        policy=policy,
        rollout_mode=AttentionRolloutMode.SHADOW,
    )


class TestAttentionStoreAppendOnly:
    def test_append_plan_and_decisions_idempotent(self) -> None:
        store = AttentionStore()
        plan = _shadow_plan()
        persisted = store.append_plan(
            plan,
            attempt_id=_ATTEMPT,
            recorded_at=_TS,
        )
        assert isinstance(persisted, PersistedAttentionPlan)
        assert persisted.attempt_id == _ATTEMPT
        again = store.append_plan(plan, attempt_id=_ATTEMPT, recorded_at=_TS)
        assert again == persisted
        assert store.decision_count_for_plan(plan.plan_id) == len(plan.decisions)

    def test_changed_plan_content_raises_conflict(self) -> None:
        store = AttentionStore()
        plan = _shadow_plan()
        store.append_plan(plan, attempt_id=_ATTEMPT, recorded_at=_TS)
        mutated = plan.model_copy(
            update={"exploration_slots_reserved": plan.exploration_slots_reserved + 1}
        )
        with pytest.raises(AttentionStoreConflict):
            store.append_plan(mutated, attempt_id=_ATTEMPT, recorded_at=_TS)

    def test_link_provider_attempt_per_decision(self) -> None:
        store = AttentionStore()
        plan = _shadow_plan()
        store.append_plan(plan, attempt_id=_ATTEMPT, recorded_at=_TS)
        decision = plan.decisions[0]
        decision_id = attention_decision_id(plan_id=plan.plan_id, target_key=decision.target_key)
        attempt_a = uuid4()
        store.link_provider_attempt(decision_id=decision_id, provider_attempt_id=attempt_a)
        store.link_provider_attempt(decision_id=decision_id, provider_attempt_id=attempt_a)
        assert store.provider_attempt_ids_for(decision_id) == (attempt_a,)

    def test_context_manifest_append_only(self) -> None:
        store = AttentionStore()
        plan = _shadow_plan()
        store.append_plan(plan, attempt_id=_ATTEMPT, recorded_at=_TS)
        decision = plan.decisions[0]
        manifest = AttentionContextManifest(
            manifest_id=uuid4(),
            plan_id=plan.plan_id,
            decision_id=attention_decision_id(plan_id=plan.plan_id, target_key=decision.target_key),
            run_id=_RUN,
            attempt_id=_ATTEMPT,
            role="h5",
            state_version_id=_STATE,
            content_hash="a" * 64,
            included_entity_ids=("evidence:abc", "belief:def"),
            omission_reasons=("token_budget",),
            recorded_at=_TS,
        )
        stored = store.append_context_manifest(manifest)
        assert stored == manifest
        assert store.append_context_manifest(manifest) == manifest


class TestAttentionStoreAsOf:
    def test_exact_as_of_excludes_future_rows(self) -> None:
        store = AttentionStore()
        plan = _shadow_plan()
        store.append_plan(plan, attempt_id=_ATTEMPT, recorded_at=_TS)
        later = _TS + timedelta(hours=1)
        plan2 = plan_research_attention(
            run_id="run-later",
            state_version_id=_STATE,
            features=[_ticker_features(ticker="NVDA")],
            rollout_mode=AttentionRolloutMode.SHADOW,
        )
        store.append_plan(plan2, attempt_id="attempt-2", recorded_at=later)

        as_of = store.load_plan_as_of(run_id=_RUN, attempt_id=_ATTEMPT, recorded_as_of=_TS)
        assert as_of is not None
        assert as_of.plan.plan_id == plan.plan_id

        before_first = store.load_plan_as_of(
            run_id=_RUN,
            attempt_id=_ATTEMPT,
            recorded_as_of=_TS - timedelta(seconds=1),
        )
        assert before_first is None

        decisions = store.load_decisions_as_of(
            plan_id=plan.plan_id,
            recorded_as_of=_TS + timedelta(minutes=30),
        )
        assert len(decisions) == len(plan.decisions)
        assert all(item.recorded_at <= _TS + timedelta(minutes=30) for item in decisions)


class TestAttentionPolicyEvaluation:
    def test_reconcile_shadow_decisions_to_planned_and_actual(self) -> None:
        store = AttentionStore()
        plan = _shadow_plan()
        store.append_plan(plan, attempt_id=_ATTEMPT, recorded_at=_TS)
        usages: dict[str, tuple[ActualProviderAttemptUsage, ...]] = {}
        for decision in plan.decisions:
            decision_id = attention_decision_id(
                plan_id=plan.plan_id, target_key=decision.target_key
            )
            if decision.mode is AttentionMode.CARRY:
                usages[decision.target_key] = ()
                continue
            attempt_id = uuid4()
            store.link_provider_attempt(decision_id=decision_id, provider_attempt_id=attempt_id)
            usages[decision.target_key] = (
                ActualProviderAttemptUsage(
                    provider_attempt_id=attempt_id,
                    prompt_tokens=100,
                    completion_tokens=50,
                    searches=1 if decision.budget.searches else 0,
                    cost_usd=Decimal("0.01"),
                ),
            )

        evaluation = store.reconcile_plan(
            plan_id=plan.plan_id,
            attempt_usages=usages,
            recorded_at=_TS,
        )
        assert isinstance(evaluation, AttentionPolicyEvaluation)
        assert evaluation.complete is True
        assert evaluation.run_id == _RUN
        assert evaluation.attempt_id == _ATTEMPT
        assert len(evaluation.decision_reconciliations) == len(plan.decisions)
        for row in evaluation.decision_reconciliations:
            assert isinstance(row, AttentionDecisionReconciliation)
            assert row.planned_budget.provider_calls >= 0
            if row.planned_budget.provider_calls == 0:
                assert row.actual_budget.provider_calls == 0
            assert row.complete is True
        stored = store.append_evaluation(evaluation)
        assert stored.evaluation_id == evaluation.evaluation_id

    def test_incomplete_telemetry_fails_evaluation(self) -> None:
        store = AttentionStore()
        plan = _shadow_plan()
        store.append_plan(plan, attempt_id=_ATTEMPT, recorded_at=_TS)
        challenge = next(d for d in plan.decisions if d.mode is not AttentionMode.CARRY)
        decision_id = attention_decision_id(plan_id=plan.plan_id, target_key=challenge.target_key)
        store.link_provider_attempt(decision_id=decision_id, provider_attempt_id=uuid4())
        evaluation = store.reconcile_plan(
            plan_id=plan.plan_id,
            attempt_usages={},  # missing actuals for non-carry decisions
            recorded_at=_TS,
        )
        assert evaluation.complete is False
        incomplete = [
            row
            for row in evaluation.decision_reconciliations
            if row.planned_budget.provider_calls > 0 and not row.complete
        ]
        assert incomplete

    def test_missing_plan_raises(self) -> None:
        store = AttentionStore()
        with pytest.raises(AttentionStoreMissingError):
            store.reconcile_plan(
                plan_id=uuid4(),
                attempt_usages={},
                recorded_at=_TS,
            )

    def test_off_rollout_skips_decision_reconciliation_requirement(self) -> None:
        store = AttentionStore()
        policy = load_research_attention_policy(default_research_policy_path())
        plan = plan_research_attention(
            run_id=_RUN,
            state_version_id=_STATE,
            features=[],
            policy=policy,
            rollout_mode=AttentionRolloutMode.OFF,
        )
        store.append_plan(plan, attempt_id=_ATTEMPT, recorded_at=_TS)
        evaluation = store.reconcile_plan(
            plan_id=plan.plan_id,
            attempt_usages={},
            recorded_at=_TS,
        )
        assert evaluation.complete is True
        assert evaluation.decision_reconciliations == ()


class TestAttentionStoreLineage:
    def test_persisted_plan_links_state_policy_and_reasons(self) -> None:
        store = AttentionStore()
        plan = _shadow_plan()
        persisted = store.append_plan(plan, attempt_id=_ATTEMPT, recorded_at=_TS)
        assert persisted.plan.state_version_id == _STATE
        assert persisted.plan.policy_content_hash
        loaded = store.load_plan(plan.plan_id)
        assert loaded.plan == plan
        for decision in plan.decisions:
            decision_id = attention_decision_id(
                plan_id=plan.plan_id, target_key=decision.target_key
            )
            row = store.load_decision(decision_id)
            assert row.decision.reason in AttentionReason
            assert row.decision.features.state_version_id == str(_STATE)
            assert row.policy_content_hash == plan.policy_content_hash

    def test_unlinked_provider_attempt_rejected(self) -> None:
        store = AttentionStore()
        with pytest.raises(AttentionStoreError):
            store.link_provider_attempt(decision_id=uuid4(), provider_attempt_id=uuid4())
