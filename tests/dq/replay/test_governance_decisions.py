"""WP16.8 — record authenticated human decisions without activation (#3007).

Red coverage: approve requires eligible evaluation; reject/defer need rationale;
rollback links evaluation + current version; identity from principal only;
immutable/superseding; no policy mutation/deploy/broker; no actor impersonation.
"""

from __future__ import annotations

import inspect
from datetime import UTC, datetime
from uuid import uuid4

import pytest
from digikey.models import DigiAuthContext
from digiquant.olympus.hermes.allocation_hashes import sha256_hex
from digiquant.olympus.replay.governance import (
    AuthenticatedPrincipal,
    GovernanceDecisionError,
    record_policy_governance_decision,
)
from digiquant.olympus.replay.governance_models import (
    GateCriteriaVersion,
    GateEvaluation,
    GovernanceDecisionKind,
    PolicyComparisonReport,
    PolicyGovernanceDecision,
)
from digiquant.olympus.replay.store import PolicyReplayStore, PolicyReplayStoreConflict
from pydantic import ValidationError

pytestmark = pytest.mark.unit

_TS = datetime(2026, 8, 27, 15, 0, tzinfo=UTC)
_HASH = "a" * 64


def _principal(*, subject: str = "key:operator-1") -> AuthenticatedPrincipal:
    return AuthenticatedPrincipal(subject=subject, principal_kind="api_key")


def _seed_evaluation(
    store: PolicyReplayStore,
    *,
    eligible: bool = True,
) -> GateEvaluation:
    comparison = PolicyComparisonReport(
        comparison_id=uuid4(),
        pair_content_hash=_HASH,
        shared_manifest_content_hash=_HASH,
        report_content_hash=sha256_hex({"cmp": str(uuid4())}),
        recorded_at=_TS,
        status="ok",
    )
    # Bypass pair/manifest FK for decision-focused unit tests by planting a
    # comparison row that append_comparison would reject without a pair.
    store._comparisons[comparison.comparison_id] = comparison
    store._comparisons_by_hash[comparison.report_content_hash] = comparison.comparison_id

    criteria = GateCriteriaVersion(
        criteria_version_id=uuid4(),
        criteria_key="promo-v1",
        content_hash=sha256_hex({"k": "promo"}),
        effective_at=_TS,
        recorded_at=_TS,
        author="human-author",
        rationale="pre-versioned",
    )
    store.append_criteria(criteria)

    evaluation = GateEvaluation(
        evaluation_id=uuid4(),
        comparison_id=comparison.comparison_id,
        criteria_version_id=criteria.criteria_version_id,
        evaluation_content_hash=sha256_hex({"eligible": eligible, "id": str(uuid4())}),
        recorded_at=_TS,
        eligible_for_human_review=eligible,
    )
    store.append_evaluation(evaluation)
    return evaluation


def test_approve_requires_eligible_evaluation() -> None:
    store = PolicyReplayStore()
    evaluation = _seed_evaluation(store, eligible=False)
    with pytest.raises(GovernanceDecisionError, match="eligible_for_human_review"):
        record_policy_governance_decision(
            store,
            principal=_principal(),
            evaluation_id=evaluation.evaluation_id,
            decision_kind=GovernanceDecisionKind.APPROVE,
            rationale="looks good",
            recorded_at=_TS,
        )


def test_approve_succeeds_when_eligible() -> None:
    store = PolicyReplayStore()
    evaluation = _seed_evaluation(store, eligible=True)
    decision = record_policy_governance_decision(
        store,
        principal=_principal(subject="bff:alice"),
        evaluation_id=evaluation.evaluation_id,
        decision_kind=GovernanceDecisionKind.APPROVE,
        rationale="criteria met after review",
        recorded_at=_TS,
    )
    assert decision.decision_kind is GovernanceDecisionKind.APPROVE
    assert decision.actor_principal == "bff:alice"
    assert decision.evaluation_id == evaluation.evaluation_id
    assert store.get_evaluation(evaluation.evaluation_id) == evaluation
    assert store.list_decisions_for_evaluation(evaluation.evaluation_id) == (decision,)


def test_reject_and_defer_allowed_with_rationale_when_ineligible() -> None:
    store = PolicyReplayStore()
    evaluation = _seed_evaluation(store, eligible=False)
    reject = record_policy_governance_decision(
        store,
        principal=_principal(),
        evaluation_id=evaluation.evaluation_id,
        decision_kind=GovernanceDecisionKind.REJECT,
        rationale="accounting breach unresolved",
        recorded_at=_TS,
    )
    assert reject.decision_kind is GovernanceDecisionKind.REJECT

    store2 = PolicyReplayStore()
    evaluation2 = _seed_evaluation(store2, eligible=False)
    defer = record_policy_governance_decision(
        store2,
        principal=_principal(),
        evaluation_id=evaluation2.evaluation_id,
        decision_kind=GovernanceDecisionKind.DEFER,
        rationale="need another fold",
        recorded_at=_TS,
    )
    assert defer.decision_kind is GovernanceDecisionKind.DEFER


def test_empty_rationale_refused() -> None:
    store = PolicyReplayStore()
    evaluation = _seed_evaluation(store, eligible=True)
    with pytest.raises(GovernanceDecisionError, match="rationale"):
        record_policy_governance_decision(
            store,
            principal=_principal(),
            evaluation_id=evaluation.evaluation_id,
            decision_kind=GovernanceDecisionKind.DEFER,
            rationale="   ",
            recorded_at=_TS,
        )


def test_rollback_review_links_evaluation_and_current_version() -> None:
    store = PolicyReplayStore()
    evaluation = _seed_evaluation(store, eligible=False)
    with pytest.raises(GovernanceDecisionError, match="current_policy_version_id"):
        record_policy_governance_decision(
            store,
            principal=_principal(),
            evaluation_id=evaluation.evaluation_id,
            decision_kind=GovernanceDecisionKind.ROLLBACK_REVIEW,
            rationale="challenger underperformed",
            recorded_at=_TS,
        )

    decision = record_policy_governance_decision(
        store,
        principal=_principal(),
        evaluation_id=evaluation.evaluation_id,
        decision_kind=GovernanceDecisionKind.ROLLBACK_REVIEW,
        rationale="challenger underperformed",
        recorded_at=_TS,
        current_policy_version_id="policy-incumbent-v3",
    )
    assert decision.current_policy_version_id == "policy-incumbent-v3"
    assert decision.evaluation_id == evaluation.evaluation_id


def test_identity_from_principal_not_caller_actor_string() -> None:
    store = PolicyReplayStore()
    evaluation = _seed_evaluation(store, eligible=True)
    sig = inspect.signature(record_policy_governance_decision)
    assert "actor_principal" not in sig.parameters
    assert "actor" not in sig.parameters

    decision = record_policy_governance_decision(
        store,
        principal=_principal(subject="key:trusted-op"),
        evaluation_id=evaluation.evaluation_id,
        decision_kind=GovernanceDecisionKind.APPROVE,
        rationale="approved by trusted principal",
        recorded_at=_TS,
    )
    assert decision.actor_principal == "key:trusted-op"

    with pytest.raises(TypeError):
        record_policy_governance_decision(  # type: ignore[call-arg]
            store,
            principal=_principal(),
            evaluation_id=evaluation.evaluation_id,
            decision_kind=GovernanceDecisionKind.APPROVE,
            rationale="spoof",
            recorded_at=_TS,
            actor_principal="attacker@evil.example",
        )


def test_authenticated_principal_from_digi_auth_context() -> None:
    ctx = DigiAuthContext(subject="key:from-jwt", principal_kind="api_key", scopes=["dq:*"])
    principal = AuthenticatedPrincipal.from_digi_auth(ctx)
    assert principal.subject == "key:from-jwt"
    assert principal.principal_kind == "api_key"

    with pytest.raises(GovernanceDecisionError, match="subject"):
        AuthenticatedPrincipal.from_digi_auth(DigiAuthContext(subject="", scopes=[]))

    with pytest.raises(ValidationError):
        AuthenticatedPrincipal(subject="", principal_kind="api_key")


def test_decision_immutable_and_superseding() -> None:
    store = PolicyReplayStore()
    evaluation = _seed_evaluation(store, eligible=True)
    first = record_policy_governance_decision(
        store,
        principal=_principal(),
        evaluation_id=evaluation.evaluation_id,
        decision_kind=GovernanceDecisionKind.DEFER,
        rationale="wait for more data",
        recorded_at=_TS,
    )
    second = record_policy_governance_decision(
        store,
        principal=_principal(subject="key:reviewer-2"),
        evaluation_id=evaluation.evaluation_id,
        decision_kind=GovernanceDecisionKind.APPROVE,
        rationale="now eligible and approved",
        recorded_at=_TS,
        supersedes_decision_id=first.decision_id,
    )
    assert second.supersedes_decision_id == first.decision_id

    mutated = first.model_copy(
        update={
            "rationale": "tampered",
            "decision_content_hash": sha256_hex({"tampered": True}),
        }
    )
    with pytest.raises(PolicyReplayStoreConflict):
        store.append_decision(mutated)


def test_recording_does_not_mutate_policy_or_activate() -> None:
    store = PolicyReplayStore()
    evaluation = _seed_evaluation(store, eligible=True)
    before_manifests = store.manifest_count()
    decision = record_policy_governance_decision(
        store,
        principal=_principal(),
        evaluation_id=evaluation.evaluation_id,
        decision_kind=GovernanceDecisionKind.APPROVE,
        rationale="record only",
        recorded_at=_TS,
    )
    assert before_manifests == store.manifest_count()
    assert store.get_evaluation(evaluation.evaluation_id) == evaluation
    # No activation / live-policy fields on the decision contract.
    assert not hasattr(decision, "activated")
    assert not hasattr(decision, "deployed")
    assert "activate" not in PolicyGovernanceDecision.model_fields
    assert decision.decision_kind is GovernanceDecisionKind.APPROVE


def test_missing_evaluation_refused() -> None:
    store = PolicyReplayStore()
    with pytest.raises(GovernanceDecisionError, match="evaluation"):
        record_policy_governance_decision(
            store,
            principal=_principal(),
            evaluation_id=uuid4(),
            decision_kind=GovernanceDecisionKind.REJECT,
            rationale="no eval",
            recorded_at=_TS,
        )
