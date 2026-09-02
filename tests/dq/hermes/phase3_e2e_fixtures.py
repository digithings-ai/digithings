"""Deterministic helpers for Integration Task 3.1 Phase 3 lock tests (#3019).

Composes WP11 evidence bundles/amendments → WP12 pinned research state →
WP13 attention routing → WP14 role context + telemetry without adding graph
nodes or runtime policy promotion.
"""

from __future__ import annotations

import ast
from datetime import UTC, date, datetime, timedelta
from pathlib import Path
from typing import Any  # score:allow untyped any — scored-lint: heterogeneous dict / client shapes
from uuid import UUID, uuid4

from digiquant.olympus.research_retrieval.context_wiring import (
    compile_h5_role_context,
    compile_h6_role_context,
    compile_h7_role_context,
    wire_h5_phase_inputs,
)
from digiquant.olympus.research_retrieval.h7_decision_context import H7PrerequisiteSnapshot
from digiquant.olympus.research_retrieval.models import (
    EvidenceBundleAmendment,
    MissingFactRequest,
    ResearchStatePin,
    TickerEvidenceBundle,
    TypedProvenance,
    evidence_bundle_amendment_content_hash,
    evidence_bundle_amendment_id,
    missing_fact_request_content_hash,
    missing_fact_request_id,
    ticker_evidence_bundle_content_hash,
    ticker_evidence_bundle_id,
)
from digiquant.olympus.research_retrieval.planner import (
    AttentionFeatures,
    AttentionRolloutMode,
    AttentionTargetKind,
    H6SelectionMode,
    build_h6_decision_features,
    load_research_attention_policy,
    plan_research_attention,
    select_h6,
)
from digiquant.olympus.research_retrieval.store import (
    ActualProviderAttemptUsage,
    EvidenceBundleStore,
    LoadedResearchState,
    ResearchStateStore,
    RoleRetrievalManifestStore,
)
from digiquant.olympus.research_retrieval.tools import (
    link_manifest_provider_tokens,
    persist_pre_call_role_manifest,
)

from tests.dq.olympus.test_context_compiler import _belief, _evidence

PHASE3_RUN_ID = "run-phase3-3019"
PHASE3_SESSION = date(2026, 8, 26)
PHASE3_CUTOFF = datetime(2026, 8, 26, 20, 0, tzinfo=UTC)
PHASE3_STATE_VERSION = UUID("dddddddd-dddd-4ddd-8ddd-dddddddddddd")

_REPO = Path(__file__).resolve().parents[3]

FORBIDDEN_PHASE3_NODES = frozenset(
    {
        "attention-planner",
        "research-planner",
        "research-attention",
        "context-compiler",
        "context-capsule",
        "evidence-bundle-writer",
        "research-state-pin",
        "h6-selection-planner",
        "h6-amendment",
        "role-retrieval",
        "manifest-persist",
        "research-state-store",
        "attention-plan-service",
        "planner-service",
    }
)

HERMES_COMPILED_NODES = frozenset(
    {
        "hermes/thesis/market-review",
        "hermes/thesis/market-exploration",
        "hermes/thesis/vehicle-map",
        "hermes/thesis/opportunity-screener",
        "hermes/portfolio/asset-analyst-worker",
        "hermes/portfolio/deliberation-worker",
        "hermes/portfolio/pm-direction",
        "hermes/portfolio/risk-sizing",
        "hermes/portfolio/commit-run",
    }
)

ATLAS_COMPILED_NODES = frozenset(
    {
        "preflight",
        "triage",
        "alt-sentiment-news",
        "alt-cta-positioning",
        "inst-institutional-flows",
        "macro",
        "bonds",
        "crypto",
        "equity",
        "sector-technology",
        "consolidate",
        "master-digest",
    }
)

PRODUCTION_GUARD_PATHS = (
    _REPO / "digiquant/src/digiquant/olympus/hermes/chain.py",
    _REPO / "digiquant/src/digiquant/olympus/hermes/graph.py",
    _REPO / "digiquant/src/digiquant/olympus/hermes/phases/h5_asset_analyst.py",
    _REPO / "digiquant/src/digiquant/olympus/hermes/phases/h6_deliberation.py",
)

ENFORCE_PROMOTION_FRAGMENTS = frozenset(
    {
        "policy_promotion",
        "enforce_canary",
        "auto_promote",
    }
)

_AMENDMENT_EVIDENCE = UUID("33333333-3333-4333-8333-333333333333")
_PROV = TypedProvenance(
    source_run_id=PHASE3_RUN_ID,
    attempt_id="attempt-1",
    artifact_id="artifact-phase3",
)
_TS = datetime(2026, 8, 26, 16, 0, tzinfo=UTC)
_EV_A = UUID("11111111-1111-4111-8111-111111111111")
_EV_B = UUID("22222222-2222-4222-8222-222222222222")


def _ticker_bundle(
    *,
    ticker: str = "AAPL",
    evidence_ids: tuple[UUID, ...] = (_EV_A, _EV_B),
    state_version_id: UUID = PHASE3_STATE_VERSION,
) -> TickerEvidenceBundle:
    content_hash = ticker_evidence_bundle_content_hash(
        ticker=ticker,
        state_version_id=state_version_id,
        evidence_ids=evidence_ids,
        source="h5:base",
    )
    return TickerEvidenceBundle(
        bundle_id=ticker_evidence_bundle_id(
            source_run_id=PHASE3_RUN_ID,
            ticker=ticker,
            content_hash=content_hash,
        ),
        ticker=ticker,
        source_run_id=PHASE3_RUN_ID,
        attempt_id="attempt-1",
        state_version_id=state_version_id,
        evidence_ids=evidence_ids,
        source="h5:base",
        event_time=_TS - timedelta(hours=2),
        effective_as_of=_TS - timedelta(hours=1),
        known_at=_TS - timedelta(minutes=30),
        recorded_at=_TS,
        schema_version=1,
        content_hash=content_hash,
        provenance=_PROV,
    )


def _missing_fact_request(bundle: TickerEvidenceBundle) -> MissingFactRequest:
    content_hash = missing_fact_request_content_hash(
        base_bundle_id=bundle.bundle_id,
        fact_key="next_earnings_date",
        rationale="H6 challenge needs dated catalyst",
    )
    return MissingFactRequest(
        request_id=missing_fact_request_id(
            base_bundle_id=bundle.bundle_id,
            fact_key="next_earnings_date",
            content_hash=content_hash,
        ),
        base_bundle_id=bundle.bundle_id,
        ticker=bundle.ticker,
        fact_key="next_earnings_date",
        rationale="H6 challenge needs dated catalyst",
        event_time=bundle.event_time,
        effective_as_of=bundle.effective_as_of,
        known_at=bundle.known_at,
        recorded_at=_TS,
        schema_version=1,
        content_hash=content_hash,
        provenance=_PROV,
    )


def _amendment(
    bundle: TickerEvidenceBundle,
    request: MissingFactRequest,
    *,
    evidence_ids: tuple[UUID, ...] | None = None,
) -> EvidenceBundleAmendment:
    ids = evidence_ids if evidence_ids is not None else (_AMENDMENT_EVIDENCE,)
    content_hash = evidence_bundle_amendment_content_hash(
        base_bundle_id=bundle.bundle_id,
        missing_fact_request_id=request.request_id,
        evidence_ids=ids,
        source="h6:missing_fact",
    )
    return EvidenceBundleAmendment(
        amendment_id=evidence_bundle_amendment_id(
            base_bundle_id=bundle.bundle_id,
            missing_fact_request_id=request.request_id,
            content_hash=content_hash,
        ),
        base_bundle_id=bundle.bundle_id,
        missing_fact_request_id=request.request_id,
        ticker=bundle.ticker,
        evidence_ids=ids,
        source="h6:missing_fact",
        event_time=_TS - timedelta(minutes=20),
        effective_as_of=_TS - timedelta(minutes=10),
        known_at=_TS - timedelta(minutes=5),
        recorded_at=_TS,
        schema_version=1,
        content_hash=content_hash,
        provenance=bundle.provenance,
    )


def phase3_pinned_research_state() -> tuple[
    ResearchStateStore, ResearchStatePin, LoadedResearchState
]:
    """Seed store, pin one version, return strict load."""
    from digiquant.olympus.research_retrieval.models import (
        ResearchStateManifest,
        ResearchStateVersion,
        content_digest,
        manifest_content_hash,
        research_state_version_id,
    )

    store = ResearchStateStore()
    ev = _evidence(summary="Filed 8-K item 2.02")
    belief = _belief(evidence=ev, statement="Soft landing remains base case")
    store.append_evidence(ev)
    store.append_belief(belief)
    known_at = max(ev.known_at, belief.known_at, _TS)
    manifest = ResearchStateManifest(
        evidence_ids=(ev.evidence_id,),
        belief_version_ids=(belief.belief_version_id,),
        expected_event_version_ids=(),
        patch_ids=(),
        legacy_ref_ids=(),
        content_hash=manifest_content_hash(
            evidence_ids=(ev.evidence_id,),
            belief_version_ids=(belief.belief_version_id,),
            expected_event_version_ids=(),
            patch_ids=(),
            legacy_ref_ids=(),
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
        event_time=_TS - timedelta(hours=1),
        effective_as_of=_TS - timedelta(minutes=30),
        known_at=known_at,
        recorded_at=max(known_at, _TS),
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
    store.append_state_version(version)
    loaded = store.load_state_version(version.state_version_id, strict=True)
    pin = ResearchStatePin(
        run_id=PHASE3_RUN_ID,
        attempt_id="attempt-1",
        state_version_id=version.state_version_id,
        knowledge_cutoff_at=PHASE3_CUTOFF,
        requested_as_of=PHASE3_CUTOFF - timedelta(minutes=5),
        pinned_at=PHASE3_CUTOFF,
    )
    store.pin_state_for_run(pin)
    return store, pin, loaded


def phase3_evidence_bundle_lineage(*, state_version_id: UUID) -> tuple[EvidenceBundleStore, bytes]:
    """Immutable base + one amendment; snapshot round-trip bytes."""
    store = EvidenceBundleStore()
    bundle = store.append_base_bundle(_ticker_bundle(state_version_id=state_version_id))
    request = store.append_missing_fact_request(_missing_fact_request(bundle))
    store.append_amendment(_amendment(bundle, request))
    snapshot = store.dump_snapshot()
    reloaded = EvidenceBundleStore.from_snapshot(snapshot)
    assert reloaded.lineage_bytes() == snapshot
    assert reloaded.load_base_bundle(bundle.bundle_id) == bundle
    assert reloaded.amendment_count_for_base(bundle.bundle_id) == 1
    return store, snapshot


def phase3_h4_roster() -> list[str]:
    return ["AAPL", "MSFT"]


def assert_research_plan_preserves_h4_roster(plan: Any, roster: list[str]) -> None:
    """WP13 planner must not expand, shrink, or reorder the H4 ticker roster."""
    expected = [t.strip().upper() for t in roster if t and t.strip()]
    ticker_keys = [
        d.target_key.upper()
        for d in plan.decisions
        if d.features.target_kind is AttentionTargetKind.TICKER
    ]
    if ticker_keys != expected:
        raise AssertionError(f"H4 roster mismatch: planner={ticker_keys!r} expected={expected!r}")


def phase3_attention_plan(*, roster: list[str] | None = None, state_version_id: UUID) -> Any:
    """Shadow attention plan over ticker + artifact targets; H4 fingerprint preserved."""
    roster = roster if roster is not None else phase3_h4_roster()
    policy = load_research_attention_policy()
    features = [
        AttentionFeatures(
            target_kind=AttentionTargetKind.TICKER,
            target_key=ticker,
            state_version_id=str(state_version_id),
            has_prior=True,
            h6=build_h6_decision_features(
                ticker=ticker,
                roster_reason="held" if ticker == "AAPL" else "technical",
                held=ticker == "AAPL",
                weight_pct=8.0 if ticker == "AAPL" else 0.0,
                analyst={"stance": "hold", "conviction_score": 2},
            ),
        )
        for ticker in roster
    ] + [
        AttentionFeatures(
            target_kind=AttentionTargetKind.ARTIFACT,
            target_key="segment:macro",
            state_version_id=str(state_version_id),
            has_prior=True,
            triage_mode="stale",
        )
    ]
    plan = plan_research_attention(
        run_id=PHASE3_RUN_ID,
        state_version_id=state_version_id,
        features=features,
        policy=policy,
        rollout_mode=AttentionRolloutMode.SHADOW,
    )
    assert_research_plan_preserves_h4_roster(plan, roster)
    assert plan.actuated is False
    return plan


def phase3_h6_selection(*, conflict: bool = False, low_value: bool = False) -> Any:
    analyst = {"stance": "buy" if conflict else "hold", "conviction_score": 3}
    prior = {"stance": "hold", "conviction_score": 2}
    features = build_h6_decision_features(
        ticker="AAPL",
        roster_reason="held",
        held=not low_value,
        weight_pct=0.5 if low_value else 8.0,
        analyst=analyst,
        prior_analyst=prior if conflict else prior,
        price_delta=0.02 if conflict else 0.001,
        has_evidence_conflict=conflict,
    )
    return select_h6(features, mode=H6SelectionMode.SHADOW)


def phase3_role_contexts(
    loaded: LoadedResearchState,
    bundle: TickerEvidenceBundle,
) -> dict[str, Any]:
    """Compile H5/H6/H7 blinded contexts from one pinned state version."""
    ev_id = loaded.evidence[0].evidence_id
    h5_capsule, h5_manifest = compile_h5_role_context(
        loaded=loaded,
        ticker=bundle.ticker,
        bundle=bundle,
        changed_evidence_ids=frozenset({ev_id}),
    )
    h5_wire = wire_h5_phase_inputs(
        {"ticker": bundle.ticker, "stance": "hold"},
        ticker=bundle.ticker,
        bundle=bundle,
        research_state_pin={"state_version_id": str(loaded.version.state_version_id)},
        changed_evidence_ids=frozenset({ev_id}),
    )
    h6_capsule, h6_manifest = compile_h6_role_context(
        loaded=loaded,
        ticker=bundle.ticker,
        bundle=bundle,
    )
    h7 = compile_h7_role_context(
        loaded=loaded,
        prerequisites=H7PrerequisiteSnapshot(state_version_id=loaded.version.state_version_id),
        focus_roster=(bundle.ticker,),
    )
    return {
        "h5_capsule": h5_capsule,
        "h5_manifest": h5_manifest,
        "h5_wire": h5_wire,
        "h6_capsule": h6_capsule,
        "h6_manifest": h6_manifest,
        "h7": h7,
    }


def phase3_telemetry_reconciliation(manifest: Any) -> Any:
    """Pre-call manifest persisted; estimated tokens unchanged after WP1 link."""
    store = RoleRetrievalManifestStore()
    persist_pre_call_role_manifest(
        store,
        run_id=PHASE3_RUN_ID,
        attempt_id="attempt-h5",
        manifest=manifest,
        recorded_at=_TS,
    )
    before_hash = manifest.content_hash
    before_tokens = manifest.estimated_tokens
    link = link_manifest_provider_tokens(
        store,
        manifest=manifest,
        usage=ActualProviderAttemptUsage(
            provider_attempt_id=uuid4(),
            prompt_tokens=900,
            completion_tokens=120,
            searches=0,
        ),
        recorded_at=_TS,
    )
    assert link.estimated_tokens == before_tokens
    assert manifest.content_hash == before_hash
    assert manifest.estimated_tokens == before_tokens
    return link


def production_imports_enforce_promotion(path: Path) -> list[str]:
    src = path.read_text(encoding="utf-8")
    tree = ast.parse(src)
    hits: list[str] = []
    for node in ast.walk(tree):
        mod = getattr(node, "module", None)
        if mod and any(fragment in mod for fragment in ENFORCE_PROMOTION_FRAGMENTS):
            hits.append(mod)
        if isinstance(node, ast.Import):
            for alias in node.names:
                if any(fragment in alias.name for fragment in ENFORCE_PROMOTION_FRAGMENTS):
                    hits.append(alias.name)
    return hits


def run_phase3_composition() -> dict[str, Any]:
    """End-to-end WP11→WP14 composition over persisted serialize/reload fixtures."""
    state_store, pin, loaded = phase3_pinned_research_state()
    original_bytes = state_store.exact_version_bytes(loaded.version.state_version_id)
    state_id = loaded.version.state_version_id

    bundle_store, bundle_snapshot = phase3_evidence_bundle_lineage(state_version_id=state_id)
    bundle_id = next(iter(bundle_store._bases))
    bundle = bundle_store.load_base_bundle(bundle_id)

    plan = phase3_attention_plan(state_version_id=state_id)
    plan_again = phase3_attention_plan(state_version_id=state_id)
    assert plan == plan_again

    selected = phase3_h6_selection(conflict=True)
    carry = phase3_h6_selection(conflict=False, low_value=True)
    contexts = phase3_role_contexts(loaded, bundle)
    telemetry = phase3_telemetry_reconciliation(contexts["h5_manifest"])

    # Newer rows must not mutate pinned exact-version bytes.
    later_ev = _evidence(summary="Post-pin filing")
    state_store.append_evidence(later_ev)
    assert state_store.exact_version_bytes(loaded.version.state_version_id) == original_bytes

    reloaded_bundles = EvidenceBundleStore.from_snapshot(bundle_snapshot)
    return {
        "state_store": state_store,
        "pin": pin,
        "loaded": loaded,
        "original_state_bytes": original_bytes,
        "bundle_store": bundle_store,
        "bundle_snapshot": bundle_snapshot,
        "reloaded_bundles": reloaded_bundles,
        "bundle": bundle,
        "plan": plan,
        "plan_again": plan_again,
        "selected_h6": selected,
        "carry_h6": carry,
        "contexts": contexts,
        "telemetry": telemetry,
    }


__all__ = [
    "ATLAS_COMPILED_NODES",
    "ENFORCE_PROMOTION_FRAGMENTS",
    "FORBIDDEN_PHASE3_NODES",
    "HERMES_COMPILED_NODES",
    "PHASE3_CUTOFF",
    "PHASE3_RUN_ID",
    "PHASE3_SESSION",
    "PHASE3_STATE_VERSION",
    "PRODUCTION_GUARD_PATHS",
    "assert_research_plan_preserves_h4_roster",
    "phase3_attention_plan",
    "phase3_evidence_bundle_lineage",
    "phase3_h4_roster",
    "phase3_h6_selection",
    "phase3_pinned_research_state",
    "phase3_role_contexts",
    "phase3_telemetry_reconciliation",
    "production_imports_enforce_promotion",
    "run_phase3_composition",
]
