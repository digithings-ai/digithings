"""WP14.1 deterministic role context capsules and manifests (#2938).

Red coverage: deterministic sort/hash, byte/token budget, exact included IDs,
every omission reason, strict role allowlist, no unpinned items, no cross-role
leakage at compile time.
"""

from __future__ import annotations

from datetime import UTC, datetime, timedelta
from decimal import Decimal
from uuid import UUID, uuid4, uuid5

import pytest
from digiquant.olympus.research_retrieval.context import (
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
from digiquant.olympus.research_retrieval.models import (
    BeliefStatus,
    BeliefVersion,
    EvidenceRecord,
    ExpectedEventStatus,
    ExpectedEventVersion,
    LegacyDocumentRef,
    PatchMode,
    PatchTargetKind,
    ResearchPatch,
    ResearchStateManifest,
    ResearchStateVersion,
    TickerEvidenceBundle,
    TypedProvenance,
    belief_content_hash,
    belief_version_id,
    content_digest,
    evidence_content_hash,
    evidence_record_id,
    expected_event_content_hash,
    expected_event_version_id,
    legacy_document_ref_id,
    manifest_content_hash,
    research_patch_content_hash,
    research_patch_id,
    research_state_version_id,
    ticker_evidence_bundle_content_hash,
    ticker_evidence_bundle_id,
)
from digiquant.olympus.research_retrieval.planner import (
    AttentionBudgetEstimate,
    AttentionDecision,
    AttentionFeatures,
    AttentionMode,
    AttentionPlan,
    AttentionReason,
    AttentionRolloutMode,
    AttentionTargetKind,
    H6DecisionFeatures,
    attention_plan_id,
)
from digiquant.olympus.research_retrieval.store import LoadedResearchState, ResearchStateStore
from pydantic import ValidationError

pytestmark = pytest.mark.unit

_TS = datetime(2026, 8, 26, 18, 0, tzinfo=UTC)
_PROV = TypedProvenance(
    source_run_id="run-wp141",
    attempt_id="attempt-1",
    artifact_id="artifact-context",
)
_TICKER = "AAPL"
_OTHER_TICKER = "MSFT"
_STATE_ID = UUID("dddddddd-dddd-4ddd-8ddd-dddddddddddd")


def _evidence(*, summary: str, belief_ids: tuple[UUID, ...] = ()) -> EvidenceRecord:
    fields = dict(
        source="ingest:sec_8k",
        authority="edgar",
        summary=summary,
        event_time=_TS - timedelta(hours=2),
        effective_as_of=_TS - timedelta(hours=1),
        known_at=_TS - timedelta(minutes=30),
        recorded_at=_TS,
        provenance=_PROV,
        affected_belief_ids=belief_ids,
        novelty_of=(),
        contradiction_of=(),
        supersedes_evidence_id=None,
    )
    digest = evidence_content_hash(
        source=fields["source"],
        authority=fields["authority"],
        summary=fields["summary"],
        affected_belief_ids=belief_ids,
        supersedes_evidence_id=None,
    )
    return EvidenceRecord(
        evidence_id=evidence_record_id(
            source=fields["source"],
            authority=fields["authority"],
            content_hash=digest,
        ),
        content_hash=digest,
        **fields,
    )


def _belief(*, evidence: EvidenceRecord, statement: str) -> BeliefVersion:
    belief_id = UUID("aaaaaaaa-aaaa-4aaa-8aaa-aaaaaaaaaaaa")
    digest = belief_content_hash(
        belief_id=belief_id,
        statement=statement,
        confidence=Decimal("0.62"),
        horizon_sessions=21,
        status=BeliefStatus.ACTIVE,
        supporting_evidence_ids=(evidence.evidence_id,),
        counter_evidence_ids=(),
        invalidation_rules=("core PCE > 3.5%",),
    )
    return BeliefVersion(
        belief_version_id=belief_version_id(
            belief_id=belief_id,
            content_hash=digest,
            supersedes_version_id=None,
        ),
        belief_id=belief_id,
        statement=statement,
        confidence=Decimal("0.62"),
        horizon_sessions=21,
        status=BeliefStatus.ACTIVE,
        supporting_evidence_ids=(evidence.evidence_id,),
        counter_evidence_ids=(),
        invalidation_rules=("core PCE > 3.5%",),
        event_time=_TS - timedelta(hours=3),
        effective_as_of=_TS - timedelta(hours=2),
        known_at=_TS - timedelta(hours=1),
        recorded_at=_TS,
        schema_version=1,
        content_hash=digest,
        provenance=_PROV,
    )


def _event(*, label: str) -> ExpectedEventVersion:
    event_id = UUID("eeeeeeee-eeee-4eee-8eee-eeeeeeeeeeee")
    event_time = _TS + timedelta(days=7)
    digest = expected_event_content_hash(
        expected_event_id=event_id,
        label=label,
        status=ExpectedEventStatus.OPEN,
        event_time=event_time,
    )
    return ExpectedEventVersion(
        expected_event_version_id=expected_event_version_id(
            expected_event_id=event_id,
            content_hash=digest,
            supersedes_version_id=None,
        ),
        expected_event_id=event_id,
        label=label,
        status=ExpectedEventStatus.OPEN,
        event_time=event_time,
        effective_as_of=_TS,
        known_at=_TS - timedelta(minutes=15),
        recorded_at=_TS,
        schema_version=1,
        content_hash=digest,
        provenance=_PROV,
    )


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


def _loaded_state(
    *,
    evidence: tuple[EvidenceRecord, ...],
    beliefs: tuple[BeliefVersion, ...] = (),
    events: tuple[ExpectedEventVersion, ...] = (),
    patches: tuple[ResearchPatch, ...] = (),
    legacy_refs: tuple[LegacyDocumentRef, ...] = (),
) -> LoadedResearchState:
    manifest = ResearchStateManifest(
        evidence_ids=tuple(item.evidence_id for item in evidence),
        belief_version_ids=tuple(item.belief_version_id for item in beliefs),
        expected_event_version_ids=tuple(item.expected_event_version_id for item in events),
        patch_ids=tuple(item.patch_id for item in patches),
        legacy_ref_ids=tuple(item.legacy_ref_id for item in legacy_refs),
        content_hash=manifest_content_hash(
            evidence_ids=tuple(item.evidence_id for item in evidence),
            belief_version_ids=tuple(item.belief_version_id for item in beliefs),
            expected_event_version_ids=tuple(item.expected_event_version_id for item in events),
            patch_ids=tuple(item.patch_id for item in patches),
            legacy_ref_ids=tuple(item.legacy_ref_id for item in legacy_refs),
        ),
    )
    version = ResearchStateVersion(
        state_version_id=research_state_version_id(
            manifest_content_hash=manifest.content_hash,
            parent_id=None,
            schema_version=1,
        ),
        parent_state_version_id=None,
        manifest=manifest,
        event_time=_TS - timedelta(hours=4),
        effective_as_of=_TS - timedelta(hours=3),
        known_at=_TS - timedelta(hours=2),
        recorded_at=_TS,
        schema_version=1,
        content_hash=content_digest(
            {
                "manifest_content_hash": manifest.content_hash,
                "parent_state_version_id": None,
                "schema_version": 1,
            }
        ),
        provenance=_PROV,
    )
    return LoadedResearchState(
        version=version,
        evidence=evidence,
        beliefs=beliefs,
        expected_events=events,
        patches=patches,
        legacy_refs=legacy_refs,
    )


def _bundle(*, state_version_id: UUID, ticker: str = _TICKER) -> TickerEvidenceBundle:
    ev = UUID("11111111-1111-4111-8111-111111111111")
    digest = ticker_evidence_bundle_content_hash(
        ticker=ticker,
        state_version_id=state_version_id,
        evidence_ids=(ev,),
        source="h5:grounding",
    )
    return TickerEvidenceBundle(
        bundle_id=ticker_evidence_bundle_id(
            source_run_id="run-wp141",
            ticker=ticker,
            content_hash=digest,
        ),
        ticker=ticker,
        source_run_id="run-wp141",
        attempt_id="attempt-1",
        state_version_id=state_version_id,
        evidence_ids=(ev,),
        source="h5:grounding",
        event_time=_TS - timedelta(hours=2),
        effective_as_of=_TS - timedelta(hours=1),
        known_at=_TS - timedelta(minutes=30),
        recorded_at=_TS,
        schema_version=1,
        content_hash=digest,
        provenance=_PROV,
    )


def _attention_plan(*, state_version_id: UUID) -> AttentionPlan:
    features = AttentionFeatures(
        target_kind=AttentionTargetKind.TICKER,
        target_key=_TICKER,
        state_version_id=state_version_id.hex,
        h6=H6DecisionFeatures(
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


def _h5_input(
    *,
    state: LoadedResearchState,
    changed: frozenset[UUID] | None = None,
    bundle: TickerEvidenceBundle | None = None,
) -> ContextCompileInput:
    return ContextCompileInput(
        role=ContextRole.H5_ANALYST,
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
    inp = _h5_input(
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
        _h5_input(state=state_fwd, changed=changed, bundle=bundle)
    )
    cap_rev, man_rev = compile_context_capsule(
        _h5_input(state=state_rev, changed=changed, bundle=bundle)
    )
    assert cap_fwd == cap_rev
    assert man_fwd == man_rev


def test_h5_rejects_unpinned_bundle_state_version() -> None:
    ev = _evidence(summary="Filed 8-K")
    state = _loaded_state(evidence=(ev,))
    wrong_pin = _bundle(state_version_id=uuid4())
    with pytest.raises(ValueError, match="state_version_id"):
        compile_context_capsule(
            _h5_input(
                state=state,
                changed=frozenset({ev.evidence_id}),
                bundle=wrong_pin,
            )
        )


def test_h5_omits_non_delta_evidence_with_reason() -> None:
    ev_changed = _evidence(summary="New filing")
    ev_stale = _evidence(summary="Old filing")
    state = _loaded_state(evidence=(ev_changed, ev_stale))
    bundle = _bundle(state_version_id=state.version.state_version_id)
    _, manifest = compile_context_capsule(
        _h5_input(
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


def test_h6_role_allowlist_rejects_beliefs_and_patches() -> None:
    ev = _evidence(summary="Bundle evidence")
    belief = _belief(evidence=ev, statement="Should not appear in H6")
    patch = _patch(summary="Metric refresh")
    state = _loaded_state(evidence=(ev,), beliefs=(belief,), patches=(patch,))
    bundle = _bundle(state_version_id=state.version.state_version_id)
    _, manifest = compile_context_capsule(
        ContextCompileInput(
            role=ContextRole.H6_DELIBERATION,
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


def test_h7_includes_attention_decisions_from_plan() -> None:
    ev = _evidence(summary="Macro read")
    belief = _belief(evidence=ev, statement="Risk-on")
    state = _loaded_state(evidence=(ev,), beliefs=(belief,))
    plan = _attention_plan(state_version_id=state.version.state_version_id)
    capsule, manifest = compile_context_capsule(
        ContextCompileInput(
            role=ContextRole.H7_PM,
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
        _h5_input(
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
    base = default_role_context_policy(ContextRole.H5_ANALYST)
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
            role=ContextRole.H5_ANALYST,
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
        _h5_input(state=state, changed=frozenset({ev.evidence_id}), bundle=bundle)
    )
    assert capsule.state_version_id == state.version.state_version_id
    assert manifest.state_version_id == state.version.state_version_id
    assert capsule.schema_version == CONTEXT_SCHEMA_VERSION
    assert manifest.schema_version == CONTEXT_SCHEMA_VERSION


def test_role_policy_hash_is_deterministic() -> None:
    h5_a = default_role_context_policy(ContextRole.H5_ANALYST).content_hash
    h5_b = default_role_context_policy(ContextRole.H5_ANALYST).content_hash
    h6 = default_role_context_policy(ContextRole.H6_DELIBERATION).content_hash
    assert h5_a == h5_b
    assert h5_a != h6


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
    inp = _h5_input(state=state, changed=frozenset({ev.evidence_id}), bundle=bundle)
    standalone = compile_context_manifest(inp)
    _, from_capsule = compile_context_capsule(inp)
    assert standalone == from_capsule


# ---------------------------------------------------------------------------
# WP14.2 — blinded H5/H6 provider wiring
# ---------------------------------------------------------------------------


def _store_with_state(state: LoadedResearchState) -> ResearchStateStore:
    store = ResearchStateStore()
    for record in state.evidence:
        store.append_evidence(record)
    for belief in state.beliefs:
        store.append_belief(belief)
    for event in state.expected_events:
        store.append_expected_event(event)
    for patch in state.patches:
        store.append_patch(patch)
    known_times = [state.version.known_at]
    known_times.extend(record.known_at for record in state.evidence)
    known_times.extend(belief.known_at for belief in state.beliefs)
    known_times.extend(event.known_at for event in state.expected_events)
    known_times.extend(patch.known_at for patch in state.patches)
    version = state.version.model_copy(
        update={
            "known_at": max(known_times),
            "recorded_at": _TS,
        }
    )
    store.append_state_version(version)
    return store


def _seed_loaded_state(
    loaded: LoadedResearchState,
) -> tuple[ResearchStateStore, dict[str, str], UUID]:
    store = _store_with_state(loaded)
    version_id = next(iter(store._versions))
    return store, {"state_version_id": str(version_id)}, version_id


def test_wire_h5_off_leaves_incumbent_inputs(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("OLYMPUS_CONTEXT_COMPILER_MODE", "off")
    ev = _evidence(summary="Filed 8-K")
    loaded = _loaded_state(evidence=(ev,))
    store, pin, version_id = _seed_loaded_state(loaded)
    bundle = _bundle(state_version_id=version_id)
    incumbent = {
        "ticker": _TICKER,
        "prior_book": [{"ticker": "MSFT", "weight_pct": 5.0}],
        "active_theses": [{"thesis_id": "t1"}],
    }
    from digiquant.olympus.research_retrieval.context_wiring import wire_h5_phase_inputs

    result = wire_h5_phase_inputs(
        incumbent,
        ticker=_TICKER,
        bundle=bundle,
        research_state_pin=pin,
        research_state_store=store,
    )
    assert result.capsule is None
    assert result.manifest is None
    assert result.phase_inputs == incumbent


def test_wire_h5_shadow_records_manifest_beside_incumbent(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setenv("OLYMPUS_CONTEXT_COMPILER_MODE", "shadow")
    ev = _evidence(summary="Filed 8-K")
    loaded = _loaded_state(evidence=(ev,))
    store, pin, version_id = _seed_loaded_state(loaded)
    bundle = _bundle(state_version_id=version_id)
    incumbent = {"ticker": _TICKER, "prior_book": [{"ticker": "MSFT"}]}
    from digiquant.olympus.research_retrieval.context_wiring import wire_h5_phase_inputs

    result = wire_h5_phase_inputs(
        incumbent,
        ticker=_TICKER,
        bundle=bundle,
        research_state_pin=pin,
        research_state_store=store,
        changed_evidence_ids=frozenset({ev.evidence_id}),
    )
    assert result.capsule is not None
    assert result.manifest is not None
    assert result.phase_inputs["prior_book"] == incumbent["prior_book"]
    assert "context_capsule_shadow" in result.phase_inputs
    assert "context_manifest_shadow" in result.phase_inputs
    assert result.phase_inputs["context_manifest_id"] == str(result.manifest.manifest_id)


def test_wire_h5_enforce_strips_portfolio_and_injects_capsule(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setenv("OLYMPUS_CONTEXT_COMPILER_MODE", "enforce")
    ev = _evidence(summary="Filed 8-K")
    belief = _belief(evidence=ev, statement="Base intact")
    loaded = _loaded_state(evidence=(ev,), beliefs=(belief,))
    store, pin, version_id = _seed_loaded_state(loaded)
    bundle = _bundle(state_version_id=version_id)
    incumbent = {
        "ticker": _TICKER,
        "prior_book": [{"ticker": "MSFT"}],
        "active_theses": [{"thesis_id": "t1"}],
        "held_in_prior_book": True,
        "weight_pct": 12.0,
    }
    from digiquant.olympus.research_retrieval.context_wiring import wire_h5_phase_inputs

    result = wire_h5_phase_inputs(
        incumbent,
        ticker=_TICKER,
        bundle=bundle,
        research_state_pin=pin,
        research_state_store=store,
        changed_evidence_ids=frozenset({ev.evidence_id}),
    )
    assert "prior_book" not in result.phase_inputs
    assert "active_theses" not in result.phase_inputs
    assert "weight_pct" not in result.phase_inputs
    assert result.phase_inputs["structured_context"] == result.capsule.body
    assert f"evidence:{ev.evidence_id}" in result.manifest.included_entity_ids


def test_wire_h6_enforce_allows_transcript_and_analyst_payload(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setenv("OLYMPUS_CONTEXT_COMPILER_MODE", "enforce")
    ev = _evidence(summary="Bundle evidence")
    loaded = _loaded_state(evidence=(ev,))
    store, pin, version_id = _seed_loaded_state(loaded)
    bundle = _bundle(state_version_id=version_id)
    incumbent = {
        "ticker": _TICKER,
        "analyst_payload": {"stance": "buy", "ticker": _TICKER},
        "transcript": [{"role": "pm", "message": "challenge"}],
        "prior_book": [{"ticker": "MSFT"}],
        "base_evidence_bundle": bundle.model_dump(mode="json"),
    }
    from digiquant.olympus.research_retrieval.context_wiring import wire_h6_phase_inputs

    result = wire_h6_phase_inputs(
        incumbent,
        ticker=_TICKER,
        bundle=bundle,
        research_state_pin=pin,
        research_state_store=store,
    )
    assert "prior_book" not in result.phase_inputs
    assert "base_evidence_bundle" not in result.phase_inputs
    assert result.phase_inputs["analyst_payload"]["stance"] == "buy"
    assert result.phase_inputs["transcript"]
    assert result.phase_inputs["structured_context"]


def test_wire_h6_rejects_unpinned_bundle_state_version(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setenv("OLYMPUS_CONTEXT_COMPILER_MODE", "enforce")
    ev = _evidence(summary="Bundle evidence")
    loaded = _loaded_state(evidence=(ev,))
    wrong_bundle = _bundle(state_version_id=uuid4())
    store, pin, _version_id = _seed_loaded_state(loaded)
    from digiquant.olympus.research_retrieval.context_wiring import wire_h6_phase_inputs

    with pytest.raises(ValueError, match="state_version_id"):
        wire_h6_phase_inputs(
            {"ticker": _TICKER},
            ticker=_TICKER,
            bundle=wrong_bundle,
            research_state_pin=pin,
            research_state_store=store,
        )
