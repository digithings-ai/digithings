"""WP14.1 deterministic role context capsules and manifests (#2938).

Red coverage: deterministic sort/hash, byte/token budget, exact included IDs,
every omission reason, strict role allowlist, no unpinned items, no cross-role
leakage at compile time."""

from __future__ import annotations

from datetime import timedelta
from uuid import UUID, uuid4, uuid5

import pytest
from digiquant.dashboard.research_retrieval.context import (
    CONTEXT_SCHEMA_VERSION,
    ContextCompileInput,
    ContextItem,
    ContextItemKind,
    ContextOmissionReason,
    ContextRole,
    RoleContextPolicy,
    compile_context_capsule,
    compile_context_manifest,
    default_role_context_policy,
    role_context_policy_content_hash,
)
from digiquant.dashboard.research_retrieval.models import (
    LegacyDocumentRef,
    PatchMode,
    PatchTargetKind,
    ResearchPatch,
    TickerEvidenceBundle,
    content_digest,
    legacy_document_ref_id,
    research_patch_content_hash,
    research_patch_id,
)
from digiquant.dashboard.research_retrieval.planner import (
    AttentionBudgetEstimate,
    AttentionDecision,
    AttentionFeatures,
    AttentionMode,
    AttentionPlan,
    AttentionReason,
    AttentionRolloutMode,
    AttentionTargetKind,
    DeliberationDecisionFeatures,
    attention_plan_id,
)
from digiquant.dashboard.research_retrieval.store import LoadedResearchState
from pydantic import ValidationError

from tests.dq.dashboard.context_compiler_support import (
    _PROV,
    _TICKER,
    _TS,
    _belief,
    _bundle,
    _evidence,
    _loaded_state,
)

pytestmark = pytest.mark.unit


def _patch(*, summary: str) -> ResearchPatch:
    target_id = "metric:revenue_growth"
    digest = research_patch_content_hash(
        target_kind=PatchTargetKind.METRIC,
        target_id=target_id,
        mode=PatchMode.METRIC_PATCH,
        summary=summary,
    )
    return ResearchPatch(
        patch_id=research_patch_id(
            target_kind=PatchTargetKind.METRIC.value,
            target_id=target_id,
            content_hash=digest,
            supersedes_patch_id=None,
        ),
        target_kind=PatchTargetKind.METRIC,
        target_id=target_id,
        mode=PatchMode.METRIC_PATCH,
        summary=summary,
        event_time=_TS - timedelta(minutes=45),
        effective_as_of=_TS - timedelta(minutes=30),
        known_at=_TS - timedelta(minutes=20),
        recorded_at=_TS,
        schema_version=1,
        content_hash=digest,
        provenance=_PROV,
    )


def _legacy_ref() -> LegacyDocumentRef:
    digest = content_digest({"document_key": "digest", "payload_hash": "abc"})
    return LegacyDocumentRef(
        legacy_ref_id=legacy_document_ref_id(
            document_key="digest",
            as_of_date="2026-08-20",
            source_hash=digest,
        ),
        document_key="digest",
        as_of_date="2026-08-20",
        source_table="documents",
        source_hash=digest,
    )


def _attention_plan(*, state_version_id: UUID) -> AttentionPlan:
    features = AttentionFeatures(
        target_kind=AttentionTargetKind.TICKER,
        target_key=_TICKER,
        state_version_id=state_version_id.hex,
        deliberation=DeliberationDecisionFeatures(
            ticker=_TICKER,
            roster_reason="held",
            held=True,
            weight_pct=1.0,
            stance="hold",
            conviction_score=1,
            raw_uncertainty="low",
        ),
    )
    decision = AttentionDecision(
        target_key=_TICKER,
        mode=AttentionMode.CHALLENGE,
        reason=AttentionReason.DECISION_BOUNDARY,
        reasons=(AttentionReason.DECISION_BOUNDARY,),
        features=features,
        budget=AttentionBudgetEstimate(provider_calls=1, searches=0, uncached_tokens=500),
    )
    policy_hash = "abc123" * 10 + "abcd"
    plan_id = attention_plan_id(
        run_id="run-wp141",
        state_version_id=state_version_id,
        policy_content_hash=policy_hash,
        target_keys=(_TICKER,),
    )
    return AttentionPlan(
        plan_id=plan_id,
        run_id="run-wp141",
        state_version_id=state_version_id,
        policy_content_hash=policy_hash,
        rollout_mode=AttentionRolloutMode.SHADOW,
        actuated=False,
        decisions=(decision,),
        total_budget=AttentionBudgetEstimate(provider_calls=1, searches=0, uncached_tokens=500),
        exploration_slots_reserved=0,
    )


def _analyst_input(
    *,
    state: LoadedResearchState,
    changed: frozenset[UUID] | None = None,
    bundle: TickerEvidenceBundle | None = None,
) -> ContextCompileInput:
    return ContextCompileInput(
        role=ContextRole.ANALYST,
        state=state,
        ticker=_TICKER,
        bundle=bundle,
        changed_evidence_ids=changed,
    )


def test_same_state_and_policy_compile_byte_identical_capsule_and_manifest() -> None:
    ev = _evidence(summary="Filed 8-K")
    belief = _belief(evidence=ev, statement="Base case intact")
    state = _loaded_state(evidence=(ev,), beliefs=(belief,))
    bundle = _bundle(state_version_id=state.version.state_version_id)
    inp = _analyst_input(
        state=state,
        changed=frozenset({ev.evidence_id}),
        bundle=bundle,
    )
    cap_a, man_a = compile_context_capsule(inp)
    cap_b, man_b = compile_context_capsule(inp)
    assert cap_a == cap_b
    assert man_a == man_b
    assert cap_a.content_hash == cap_b.content_hash
    assert man_a.content_hash == man_b.content_hash
    assert cap_a.manifest_id == man_a.manifest_id


def test_compile_is_independent_of_candidate_input_order() -> None:
    ev_a = _evidence(summary="First filing")
    ev_b = _evidence(summary="Second filing")
    belief = _belief(evidence=ev_a, statement="Ordered belief")
    state_fwd = _loaded_state(evidence=(ev_a, ev_b), beliefs=(belief,))
    state_rev = _loaded_state(evidence=(ev_b, ev_a), beliefs=(belief,))
    changed = frozenset({ev_a.evidence_id, ev_b.evidence_id})
    bundle = _bundle(state_version_id=state_fwd.version.state_version_id)
    cap_fwd, man_fwd = compile_context_capsule(
        _analyst_input(state=state_fwd, changed=changed, bundle=bundle)
    )
    cap_rev, man_rev = compile_context_capsule(
        _analyst_input(state=state_rev, changed=changed, bundle=bundle)
    )
    assert cap_fwd == cap_rev
    assert man_fwd == man_rev


def test_analyst_rejects_unpinned_bundle_state_version() -> None:
    ev = _evidence(summary="Filed 8-K")
    state = _loaded_state(evidence=(ev,))
    wrong_pin = _bundle(state_version_id=uuid4())
    with pytest.raises(ValueError, match="state_version_id"):
        compile_context_capsule(
            _analyst_input(
                state=state,
                changed=frozenset({ev.evidence_id}),
                bundle=wrong_pin,
            )
        )


def test_analyst_omits_non_delta_evidence_with_reason() -> None:
    ev_changed = _evidence(summary="New filing")
    ev_stale = _evidence(summary="Old filing")
    state = _loaded_state(evidence=(ev_changed, ev_stale))
    bundle = _bundle(state_version_id=state.version.state_version_id)
    _, manifest = compile_context_capsule(
        _analyst_input(
            state=state,
            changed=frozenset({ev_changed.evidence_id}),
            bundle=bundle,
        )
    )
    included = set(manifest.included_entity_ids)
    assert f"evidence:{ev_changed.evidence_id}" in included
    assert f"evidence:{ev_stale.evidence_id}" not in included
    stale_omissions = [
        item for item in manifest.omissions if item.entity_id == f"evidence:{ev_stale.evidence_id}"
    ]
    assert len(stale_omissions) == 1
    assert stale_omissions[0].reason is ContextOmissionReason.NOT_IN_DELTA


def test_deliberation_role_allowlist_rejects_beliefs_and_patches() -> None:
    ev = _evidence(summary="Bundle evidence")
    belief = _belief(evidence=ev, statement="Should not appear in deliberation")
    patch = _patch(summary="Metric refresh")
    state = _loaded_state(evidence=(ev,), beliefs=(belief,), patches=(patch,))
    bundle = _bundle(state_version_id=state.version.state_version_id)
    _, manifest = compile_context_capsule(
        ContextCompileInput(
            role=ContextRole.DELIBERATION,
            state=state,
            ticker=_TICKER,
            bundle=bundle,
        )
    )
    included = set(manifest.included_entity_ids)
    assert f"ticker_bundle:{bundle.bundle_id}" in included
    assert f"belief:{belief.belief_version_id}" not in included
    assert f"patch:{patch.patch_id}" not in included
    reasons = {item.reason for item in manifest.omissions}
    assert ContextOmissionReason.ROLE_NOT_ALLOWED in reasons


def test_direction_includes_attention_decisions_from_plan() -> None:
    ev = _evidence(summary="Macro read")
    belief = _belief(evidence=ev, statement="Risk-on")
    state = _loaded_state(evidence=(ev,), beliefs=(belief,))
    plan = _attention_plan(state_version_id=state.version.state_version_id)
    capsule, manifest = compile_context_capsule(
        ContextCompileInput(
            role=ContextRole.DIRECTION,
            state=state,
            attention_plan=plan,
        )
    )
    decision = plan.decisions[0]
    decision_entity = uuid5(
        UUID("c1a0e50a-4b8d-5f2a-9c17-3d6e8f0a1b22"),
        decision.target_key,
    )
    assert any(item.kind is ContextItemKind.ATTENTION_DECISION for item in capsule.items)
    assert f"attention_decision:{decision_entity}" in manifest.included_entity_ids


def test_legacy_refs_always_omitted_with_reason() -> None:
    ev = _evidence(summary="Current evidence")
    legacy = _legacy_ref()
    state = _loaded_state(evidence=(ev,), legacy_refs=(legacy,))
    bundle = _bundle(state_version_id=state.version.state_version_id)
    _, manifest = compile_context_capsule(
        _analyst_input(
            state=state,
            changed=frozenset({ev.evidence_id}),
            bundle=bundle,
        )
    )
    assert f"legacy_ref:{legacy.legacy_ref_id}" not in manifest.included_entity_ids
    legacy_omissions = [
        item for item in manifest.omissions if item.kind is ContextItemKind.LEGACY_REF
    ]
    assert len(legacy_omissions) == 1
    assert legacy_omissions[0].reason is ContextOmissionReason.LEGACY_MANIFEST_ONLY


def test_byte_budget_emits_omission_for_truncated_items() -> None:
    ev = _evidence(summary="x" * 400)
    state = _loaded_state(evidence=(ev,))
    bundle = _bundle(state_version_id=state.version.state_version_id)
    base = default_role_context_policy(ContextRole.ANALYST)
    tight = RoleContextPolicy(
        role=base.role,
        allowed_kinds=base.allowed_kinds,
        max_bytes=120,
        max_estimated_tokens=base.max_estimated_tokens,
        requires_ticker=base.requires_ticker,
        delta_evidence_only=base.delta_evidence_only,
        content_hash=role_context_policy_content_hash(
            base.role,
            allowed_kinds=base.allowed_kinds,
            max_bytes=120,
            max_estimated_tokens=base.max_estimated_tokens,
            requires_ticker=base.requires_ticker,
            delta_evidence_only=base.delta_evidence_only,
        ),
    )
    _, manifest = compile_context_capsule(
        ContextCompileInput(
            role=ContextRole.ANALYST,
            state=state,
            ticker=_TICKER,
            bundle=bundle,
            changed_evidence_ids=frozenset({ev.evidence_id}),
            policy=tight,
        )
    )
    assert any(
        item.reason is ContextOmissionReason.BYTE_BUDGET_EXCEEDED for item in manifest.omissions
    )


def test_manifest_and_capsule_embed_state_version_and_schema() -> None:
    ev = _evidence(summary="Filed 8-K")
    state = _loaded_state(evidence=(ev,))
    bundle = _bundle(state_version_id=state.version.state_version_id)
    capsule, manifest = compile_context_capsule(
        _analyst_input(state=state, changed=frozenset({ev.evidence_id}), bundle=bundle)
    )
    assert capsule.state_version_id == state.version.state_version_id
    assert manifest.state_version_id == state.version.state_version_id
    assert capsule.schema_version == CONTEXT_SCHEMA_VERSION
    assert manifest.schema_version == CONTEXT_SCHEMA_VERSION


def test_role_policy_hash_is_deterministic() -> None:
    analyst_a = default_role_context_policy(ContextRole.ANALYST).content_hash
    analyst_b = default_role_context_policy(ContextRole.ANALYST).content_hash
    h6 = default_role_context_policy(ContextRole.DELIBERATION).content_hash
    assert analyst_a == analyst_b
    assert analyst_a != h6


def test_models_reject_extra_fields() -> None:
    with pytest.raises(ValidationError):
        ContextItem(
            kind=ContextItemKind.EVIDENCE,
            entity_id=uuid4(),
            state_version_id=uuid4(),
            content_hash="abc",
            byte_size=1,
            unexpected="nope",  # type: ignore[call-arg]
        )


def test_compile_manifest_standalone_matches_capsule_manifest() -> None:
    ev = _evidence(summary="Filed 8-K")
    state = _loaded_state(evidence=(ev,))
    bundle = _bundle(state_version_id=state.version.state_version_id)
    inp = _analyst_input(state=state, changed=frozenset({ev.evidence_id}), bundle=bundle)
    standalone = compile_context_manifest(inp)
    _, from_capsule = compile_context_capsule(inp)
    assert standalone == from_capsule
