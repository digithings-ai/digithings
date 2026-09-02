"""WP14.3 — H7 decision context compiler wiring (#2946).

Red coverage: mandate, calibration, contribution/cost, pre-trade risk, prior
authorization, unresolved/matured forecast sections; exact IDs; shadow degraded
inputs; enforce refuses unversioned dependency; no target weights.
"""

from __future__ import annotations

from datetime import UTC, datetime, timedelta
from decimal import Decimal
from uuid import UUID

import pytest
from digiquant.dashboard.research_retrieval.context_wiring import wire_h7_phase_inputs
from digiquant.dashboard.research_retrieval.h7_decision_context import (
    H7DecisionContextCompileInput,
    H7PrerequisiteSnapshot,
    H7SectionAvailability,
    H7SectionKind,
    assert_h7_no_target_weights,
    compile_h7_decision_context,
)
from digiquant.dashboard.research_retrieval.models import (
    BeliefStatus,
    BeliefVersion,
    EvidenceRecord,
    ResearchStateManifest,
    ResearchStateVersion,
    TypedProvenance,
    belief_content_hash,
    belief_version_id,
    content_digest,
    evidence_content_hash,
    evidence_record_id,
    manifest_content_hash,
    research_state_version_id,
)
from digiquant.dashboard.research_retrieval.store import LoadedResearchState, ResearchStateStore

pytestmark = pytest.mark.unit

_TS = datetime(2026, 8, 26, 18, 0, tzinfo=UTC)
_PROV = TypedProvenance(
    source_run_id="run-h7",
    attempt_id="attempt-h7",
    artifact_id="artifact-h7",
)
_STATE_ID = UUID("dddddddd-dddd-4ddd-8ddd-dddddddddddd")
_OTHER_STATE_ID = UUID("cccccccc-cccc-4ccc-8ccc-cccccccccccc")
_ACCOUNTING_ID = UUID("aaaaaaaa-aaaa-4aaa-8aaa-aaaaaaaaaaaa")
_OUTCOME_ID = UUID("bbbbbbbb-bbbb-4bbb-8bbb-bbbbbbbbbbbb")
_EFFECTIVE_ID = "eff-forecast-001"
_TICKER = "AAPL"


def _evidence(*, summary: str) -> EvidenceRecord:
    fields = dict(
        source="ingest:sec_8k",
        authority="edgar",
        summary=summary,
        event_time=_TS - timedelta(hours=2),
        effective_as_of=_TS - timedelta(hours=1),
        known_at=_TS - timedelta(minutes=30),
        recorded_at=_TS,
        provenance=_PROV,
        affected_belief_ids=(),
        novelty_of=(),
        contradiction_of=(),
        supersedes_evidence_id=None,
    )
    digest = evidence_content_hash(
        source=fields["source"],
        authority=fields["authority"],
        summary=fields["summary"],
        affected_belief_ids=(),
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


def _loaded_state(
    *,
    evidence: tuple[EvidenceRecord, ...],
    beliefs: tuple[BeliefVersion, ...] = (),
) -> LoadedResearchState:
    manifest = ResearchStateManifest(
        evidence_ids=tuple(item.evidence_id for item in evidence),
        belief_version_ids=tuple(item.belief_version_id for item in beliefs),
        expected_event_version_ids=(),
        patch_ids=(),
        legacy_ref_ids=(),
        content_hash=manifest_content_hash(
            evidence_ids=tuple(item.evidence_id for item in evidence),
            belief_version_ids=tuple(item.belief_version_id for item in beliefs),
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
        expected_events=(),
        patches=(),
        legacy_refs=(),
    )


def _store_with_state(loaded: LoadedResearchState) -> tuple[ResearchStateStore, dict[str, str]]:
    store = ResearchStateStore()
    for record in loaded.evidence:
        store.append_evidence(record)
    for belief in loaded.beliefs:
        store.append_belief(belief)
    version = loaded.version.model_copy(update={"known_at": _TS, "recorded_at": _TS})
    store.append_state_version(version)
    version_id = next(iter(store._versions))
    return store, {"state_version_id": str(version_id)}


def _prerequisites(*, state_version_id: UUID | None = None) -> H7PrerequisiteSnapshot:
    loaded = _loaded_state(evidence=(_evidence(summary="pin"),))
    pin_id = state_version_id or loaded.version.state_version_id
    return H7PrerequisiteSnapshot(
        state_version_id=pin_id,
        accounting_period_id=_ACCOUNTING_ID,
        accounting_period_content_hash=content_digest({"period": "2026-08-25"}),
        matured_forecast_outcome_ids=(str(_OUTCOME_ID),),
        unresolved_forecast_effective_ids=(_EFFECTIVE_ID,),
    )


def test_h7_sections_all_typed_or_unavailable() -> None:
    ev = _evidence(summary="Macro read")
    belief = _belief(evidence=ev, statement="Risk-on")
    loaded = _loaded_state(evidence=(ev,), beliefs=(belief,))
    ctx = compile_h7_decision_context(
        H7DecisionContextCompileInput(
            loaded=loaded,
            prerequisites=_prerequisites(),
            analyst_payloads={_TICKER: {"stance": "buy", "ticker": _TICKER}},
            deliberation_summaries={
                _TICKER: {
                    "effective_forecast_id": _EFFECTIVE_ID,
                    "base_forecast_id": "base-001",
                }
            },
            shadow_calibrations={"cal-1": {"calibration_id": "cal-1"}},
            calibrated_forecasts={_TICKER: {"calibrated_forecast_id": "cf-1", "ticker": _TICKER}},
            prior_direction={"date": "2026-08-25"},
            decision_lessons=({"decision_id": "dec-1"},),
            focus_roster=(_TICKER,),
        )
    )
    kinds = {section.kind for section in ctx.sections}
    assert kinds == set(H7SectionKind)
    mandate = next(s for s in ctx.sections if s.kind is H7SectionKind.MANDATE)
    assert f"analyst:{_TICKER}" in mandate.entity_ids
    assert f"effective_forecast:{_EFFECTIVE_ID}" in mandate.entity_ids
    matured = next(s for s in ctx.sections if s.kind is H7SectionKind.MATURED_FORECASTS)
    assert f"forecast_outcome:{_OUTCOME_ID}" in matured.entity_ids
    unresolved = next(s for s in ctx.sections if s.kind is H7SectionKind.UNRESOLVED_FORECASTS)
    assert f"effective_forecast:{_EFFECTIVE_ID}" in unresolved.entity_ids
    contrib = next(s for s in ctx.sections if s.kind is H7SectionKind.CONTRIBUTION_COST)
    assert f"accounting_period:{_ACCOUNTING_ID}" in contrib.entity_ids
    risk = next(s for s in ctx.sections if s.kind is H7SectionKind.PRE_TRADE_RISK)
    assert risk.availability is H7SectionAvailability.UNAVAILABLE
    assert risk.unavailable_reason == "pre_trade_risk_report_not_yet_built_at_h7"


def test_h7_enforce_refuses_unversioned_prerequisite_state() -> None:
    ev = _evidence(summary="Macro read")
    loaded = _loaded_state(evidence=(ev,))
    bad = _prerequisites(state_version_id=_OTHER_STATE_ID)
    with pytest.raises(ValueError, match="state_version_id"):
        compile_h7_decision_context(
            H7DecisionContextCompileInput(
                loaded=loaded,
                prerequisites=bad,
                enforce_version_pin=True,
            )
        )


def test_h7_enforce_refuses_missing_prerequisites() -> None:
    ev = _evidence(summary="Macro read")
    loaded = _loaded_state(evidence=(ev,))
    with pytest.raises(ValueError, match="h7_prerequisite_snapshot"):
        compile_h7_decision_context(
            H7DecisionContextCompileInput(
                loaded=loaded,
                prerequisites=None,
                enforce_version_pin=True,
            )
        )


def test_h7_no_target_weights_in_structured_body() -> None:
    ev = _evidence(summary="Macro read")
    loaded = _loaded_state(evidence=(ev,))
    ctx = compile_h7_decision_context(
        H7DecisionContextCompileInput(
            loaded=loaded,
            prerequisites=_prerequisites(),
            analyst_payloads={
                _TICKER: {
                    "stance": "buy",
                    "recommended_weight_pct": 12.0,
                }
            },
            focus_roster=(_TICKER,),
        )
    )
    assert_h7_no_target_weights(ctx.structured_body)


def test_wire_h7_off_leaves_incumbent_inputs(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("OLYMPUS_CONTEXT_COMPILER_MODE", "off")
    ev = _evidence(summary="Macro read")
    loaded = _loaded_state(evidence=(ev,))
    store, pin = _store_with_state(loaded)
    incumbent = {
        "analyst_payloads": {"AAPL": {"stance": "buy"}},
        "portfolio_performance": {"nav": 100.0},
    }
    result = wire_h7_phase_inputs(
        incumbent,
        research_state_pin=pin,
        research_state_store=store,
        h7_prerequisite_snapshot=_prerequisites().model_dump(mode="json"),
    )
    assert result.capsule is None
    assert result.phase_inputs == incumbent


def test_wire_h7_shadow_records_manifest_and_degraded_flag(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setenv("OLYMPUS_CONTEXT_COMPILER_MODE", "shadow")
    ev = _evidence(summary="Macro read")
    loaded = _loaded_state(evidence=(ev,))
    store, pin = _store_with_state(loaded)
    incumbent = {
        "analyst_payloads": {"AAPL": {"stance": "buy"}},
        "portfolio_performance": {"nav": 100.0},
    }
    result = wire_h7_phase_inputs(
        incumbent,
        research_state_pin=pin,
        research_state_store=store,
        h7_prerequisite_snapshot=None,
        analyst_payloads={"AAPL": {"stance": "buy"}},
        focus_roster=("AAPL",),
    )
    assert result.h7_decision_context is not None
    assert result.phase_inputs["portfolio_performance"] == incumbent["portfolio_performance"]
    assert "context_capsule_shadow" in result.phase_inputs
    assert "h7_decision_context_shadow" in result.phase_inputs
    assert result.phase_inputs.get("h7_context_degraded") == "missing_versioned_prerequisites"


def test_wire_h7_enforce_injects_structured_context_without_weights(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setenv("OLYMPUS_CONTEXT_COMPILER_MODE", "enforce")
    ev = _evidence(summary="Macro read")
    loaded = _loaded_state(evidence=(ev,))
    store, pin = _store_with_state(loaded)
    incumbent = {
        "analyst_payloads": {"AAPL": {"stance": "buy"}},
        "portfolio_performance": {"nav": 100.0},
        "target_pct": 0.12,
    }
    prereq = H7PrerequisiteSnapshot(
        state_version_id=loaded.version.state_version_id,
        accounting_period_id=_ACCOUNTING_ID,
        accounting_period_content_hash=content_digest({"period": "2026-08-25"}),
        matured_forecast_outcome_ids=(str(_OUTCOME_ID),),
        unresolved_forecast_effective_ids=(_EFFECTIVE_ID,),
    )
    result = wire_h7_phase_inputs(
        incumbent,
        research_state_pin=pin,
        research_state_store=store,
        h7_prerequisite_snapshot=prereq.model_dump(mode="json"),
        analyst_payloads={"AAPL": {"stance": "buy"}},
        deliberation_summaries={
            "AAPL": {"effective_forecast_id": _EFFECTIVE_ID},
        },
        focus_roster=("AAPL",),
    )
    assert "portfolio_performance" not in result.phase_inputs
    assert "target_pct" not in result.phase_inputs
    assert "structured_context" in result.phase_inputs
    assert result.h7_decision_context is not None
    assert f"effective_forecast:{_EFFECTIVE_ID}" in next(
        s.entity_ids for s in result.h7_decision_context.sections if s.kind is H7SectionKind.MANDATE
    )
