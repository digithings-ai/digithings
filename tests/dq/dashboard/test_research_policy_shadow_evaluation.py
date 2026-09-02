"""WP13.5 — reconcile attention budgets and evaluate shadow decisions (#2934)."""

from __future__ import annotations

from datetime import UTC, datetime
from decimal import Decimal
from uuid import UUID, uuid4

import pytest
from digiquant.olympus.research_retrieval.planner import (
    AttentionMode,
    AttentionReason,
    AttentionRolloutMode,
    AttentionTargetKind,
    H6DecisionFeatures,
    attention_decision_id,
    default_research_policy_path,
    load_research_attention_policy,
    plan_research_attention,
)
from digiquant.olympus.research_retrieval.shadow_evaluation import (
    AttentionDownstreamOutcomes,
    ResearchPolicyShadowEvaluationReport,
    ShadowProviderAttemptDetail,
    evaluate_research_policy_shadow,
)
from digiquant.olympus.research_retrieval.store import AttentionStore

pytestmark = pytest.mark.unit

_TS = datetime(2026, 8, 26, 16, 0, tzinfo=UTC)
_RUN = "run-wp135"
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
        features=[
            _ticker_features(),
            _ticker_features(ticker="MSFT", weight_pct=0.5, held=False, exploration_slot=True),
        ],
        policy=policy,
        rollout_mode=AttentionRolloutMode.SHADOW,
    )


def _seed_store_with_links(store: AttentionStore) -> tuple[UUID, dict[str, tuple[ShadowProviderAttemptDetail, ...]]]:
    plan = _shadow_plan()
    store.append_plan(plan, attempt_id=_ATTEMPT, recorded_at=_TS)
    details: dict[str, tuple[ShadowProviderAttemptDetail, ...]] = {}
    for decision in plan.decisions:
        if decision.mode is AttentionMode.CARRY:
            details[decision.target_key] = ()
            continue
        attempt_id = uuid4()
        decision_id = attention_decision_id(plan_id=plan.plan_id, target_key=decision.target_key)
        store.link_provider_attempt(decision_id=decision_id, provider_attempt_id=attempt_id)
        details[decision.target_key] = (
            ShadowProviderAttemptDetail(
                provider_attempt_id=attempt_id,
                node_run_id="node-h5-aapl",
                prompt_tokens=120,
                completion_tokens=80,
                cached_prompt_tokens=10,
                cached_completion_tokens=5,
                searches=1 if decision.budget.searches else 0,
                cost_usd=Decimal("0.02"),
                latency_ms=450,
            ),
        )
    return plan.plan_id, details


def _downstream_for_plan(plan) -> dict[str, AttentionDownstreamOutcomes]:
    rows: dict[str, AttentionDownstreamOutcomes] = {}
    for decision in plan.decisions:
        if decision.mode is AttentionMode.CARRY:
            rows[decision.target_key] = AttentionDownstreamOutcomes(
                target_key=decision.target_key,
                node_run_id="node-carry",
                carried=True,
            )
        elif decision.reason is AttentionReason.EXPLORATION:
            rows[decision.target_key] = AttentionDownstreamOutcomes(
                target_key=decision.target_key,
                node_run_id="node-h5-explore",
                exploration_slot=True,
                forecast_assessment_id="forecast-msft-1",
                artifact_refs=("bundle:msft-1",),
            )
        else:
            rows[decision.target_key] = AttentionDownstreamOutcomes(
                target_key=decision.target_key,
                node_run_id="node-h5-challenge",
                amendment_id="amend-aapl-1",
                forecast_assessment_id="forecast-aapl-1",
                artifact_refs=("bundle:aapl-1",),
            )
    return rows


class TestResearchPolicyShadowEvaluation:
    def test_complete_shadow_run_reconciles_all_decisions(self) -> None:
        store = AttentionStore()
        plan_id, attempt_details = _seed_store_with_links(store)
        plan = store.load_plan(plan_id).plan
        downstream = _downstream_for_plan(plan)

        report = evaluate_research_policy_shadow(
            store,
            plan_id=plan_id,
            attempt_details=attempt_details,
            downstream_by_target=downstream,
            recorded_at=_TS,
        )

        assert isinstance(report, ResearchPolicyShadowEvaluationReport)
        assert report.eligible is True
        assert report.complete is True
        assert report.telemetry_complete is True
        assert report.downstream_complete is True
        assert report.reconciliation_rate == Decimal("1")
        assert report.evaluation.complete is True
        assert len(report.decision_rows) == len(plan.decisions)
        for row in report.decision_rows:
            assert row.complete is True
            if row.reconciliation.mode is AttentionMode.CARRY:
                assert row.attempt_details == ()
                assert row.downstream is not None
                assert row.downstream.carried is True
            else:
                assert row.attempt_details
                assert row.attempt_details[0].latency_ms == 450
                assert row.attempt_details[0].cached_tokens == 15

    def test_missing_telemetry_fails_evaluation(self) -> None:
        store = AttentionStore()
        plan_id, attempt_details = _seed_store_with_links(store)
        plan = store.load_plan(plan_id).plan
        downstream = _downstream_for_plan(plan)
        challenge = next(d for d in plan.decisions if d.mode is not AttentionMode.CARRY)
        attempt_details = dict(attempt_details)
        attempt_details.pop(challenge.target_key)

        report = evaluate_research_policy_shadow(
            store,
            plan_id=plan_id,
            attempt_details=attempt_details,
            downstream_by_target=downstream,
            recorded_at=_TS,
        )

        assert report.complete is False
        assert report.telemetry_complete is False
        assert report.reconciliation_rate < Decimal("1")
        incomplete = [row for row in report.decision_rows if not row.telemetry_complete]
        assert incomplete

    def test_missing_downstream_fails_evaluation(self) -> None:
        store = AttentionStore()
        plan_id, attempt_details = _seed_store_with_links(store)

        report = evaluate_research_policy_shadow(
            store,
            plan_id=plan_id,
            attempt_details=attempt_details,
            downstream_by_target={},
            recorded_at=_TS,
        )

        assert report.complete is False
        assert report.downstream_complete is False

    def test_off_rollout_not_eligible_but_complete(self) -> None:
        store = AttentionStore()
        policy = load_research_attention_policy(default_research_policy_path())
        plan = plan_research_attention(
            run_id=_RUN,
            state_version_id=_STATE,
            features=[_ticker_features()],
            policy=policy,
            rollout_mode=AttentionRolloutMode.OFF,
        )
        store.append_plan(plan, attempt_id=_ATTEMPT, recorded_at=_TS)

        report = evaluate_research_policy_shadow(
            store,
            plan_id=plan.plan_id,
            attempt_details={},
            downstream_by_target={},
            recorded_at=_TS,
        )

        assert report.eligible is False
        assert report.evaluation.complete is True

    def test_carry_downstream_must_mark_carried(self) -> None:
        store = AttentionStore()
        policy = load_research_attention_policy(default_research_policy_path())
        plan = plan_research_attention(
            run_id=_RUN,
            state_version_id=_STATE,
            features=[_ticker_features(weight_pct=0.1, conviction_score=0)],
            policy=policy,
            rollout_mode=AttentionRolloutMode.SHADOW,
        )
        store.append_plan(plan, attempt_id=_ATTEMPT, recorded_at=_TS)
        carry = next(d for d in plan.decisions if d.mode is AttentionMode.CARRY)
        downstream = {
            carry.target_key: AttentionDownstreamOutcomes(
                target_key=carry.target_key,
                carried=False,
            )
        }

        report = evaluate_research_policy_shadow(
            store,
            plan_id=plan.plan_id,
            attempt_details={carry.target_key: ()},
            downstream_by_target=downstream,
            recorded_at=_TS,
        )

        assert report.downstream_complete is False
        assert report.complete is False
