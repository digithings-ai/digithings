"""WP14.2 — wire blinded analyst/deliberation context capsules into provider phase_inputs."""

from __future__ import annotations

import logging
from dataclasses import dataclass
from enum import StrEnum
from typing import Any  # score:allow untyped any — scored-lint: heterogeneous dict / client shapes
from uuid import UUID

from digiquant.dashboard.envcompat import CONTEXT_COMPILER_MODE, env_lookup
from digiquant.dashboard.research_retrieval.blinding import (
    assert_blinded_analyst_prompt,
    assert_blinded_deliberation_prompt,
    strip_blinded_forbidden_keys,
)
from digiquant.dashboard.research_retrieval.context import (
    ContextCapsule,
    ContextCompileInput,
    ContextManifest,
    ContextRole,
    compile_context_capsule,
)
from digiquant.dashboard.research_retrieval.direction_decision_context import (
    DirectionDecisionContext,
    DirectionDecisionContextCompileInput,
    DirectionPrerequisiteSnapshot,
    assert_direction_no_target_weights,
    compile_direction_decision_context,
    strip_direction_weight_keys,
)
from digiquant.dashboard.research_retrieval.models import (
    EvidenceBundleAmendment,
    TickerEvidenceBundle,
)
from digiquant.dashboard.research_retrieval.planner import AttentionPlan
from digiquant.dashboard.research_retrieval.store import (
    LoadedResearchState,
    ResearchStateMissingError,
    ResearchStateStore,
)

logger = logging.getLogger(__name__)

DIGIQUANT_CONTEXT_COMPILER_MODE_ENV = "DIGIQUANT_CONTEXT_COMPILER_MODE"


class ContextCompilerMode(StrEnum):
    """Rollout knob for role context compiler wiring (off|shadow|enforce)."""

    OFF = "off"
    SHADOW = "shadow"
    ENFORCE = "enforce"


@dataclass(frozen=True)
class RoleContextWireResult:
    """Outcome of applying context compiler wiring to one provider call."""

    phase_inputs: dict[str, Any]
    capsule: ContextCapsule | None
    manifest: ContextManifest | None
    mode: ContextCompilerMode
    direction_decision_context: DirectionDecisionContext | None = None


def resolve_context_compiler_mode() -> ContextCompilerMode:
    """Read ``DIGIQUANT_CONTEXT_COMPILER_MODE``; unknown values → shadow."""
    raw = env_lookup(CONTEXT_COMPILER_MODE, default="shadow").strip().lower()
    try:
        return ContextCompilerMode(raw)
    except ValueError:
        logger.warning(
            "invalid %s=%r; using shadow (allowed: off|shadow|enforce)",
            DIGIQUANT_CONTEXT_COMPILER_MODE_ENV,
            raw,
        )
        return ContextCompilerMode.SHADOW


def try_load_pinned_research_state(
    store: ResearchStateStore | None,
    research_state_pin: dict[str, object] | None,
) -> LoadedResearchState | None:
    """Load exact pinned state when store + pin are available."""
    if store is None or not isinstance(research_state_pin, dict):
        return None
    raw_id = research_state_pin.get("state_version_id")
    if raw_id is None or not str(raw_id).strip():
        return None
    try:
        version_id = UUID(str(raw_id))
    except ValueError:
        return None
    try:
        return store.load_state_version(version_id, strict=True)
    except ResearchStateMissingError:
        logger.warning("pinned state_version_id %s not found in store", version_id)
        return None


def changed_evidence_ids_from_bundle(bundle: TickerEvidenceBundle) -> frozenset[UUID]:
    """Default analyst delta set: evidence IDs referenced by the pinned bundle."""
    return frozenset(bundle.evidence_ids)


def compile_analyst_role_context(
    *,
    loaded: LoadedResearchState,
    ticker: str,
    bundle: TickerEvidenceBundle,
    changed_evidence_ids: frozenset[UUID] | None = None,
) -> tuple[ContextCapsule, ContextManifest]:
    """Compile bounded analyst capsule from pinned state + bundle."""
    delta = changed_evidence_ids or changed_evidence_ids_from_bundle(bundle)
    return compile_context_capsule(
        ContextCompileInput(
            role=ContextRole.ANALYST,
            state=loaded,
            ticker=ticker,
            bundle=bundle,
            changed_evidence_ids=delta,
        )
    )


def compile_direction_role_context(
    *,
    loaded: LoadedResearchState,
    prerequisites: DirectionPrerequisiteSnapshot | None,
    attention_plan: AttentionPlan | None = None,
    analyst_payloads: dict[str, dict[str, Any]] | None = None,
    deliberation_summaries: dict[str, dict[str, Any]] | None = None,
    shadow_calibrations: dict[str, dict[str, Any]] | None = None,
    calibrated_forecasts: dict[str, dict[str, Any]] | None = None,
    prior_direction: dict[str, Any] | None = None,
    decision_lessons: tuple[dict[str, Any], ...] = (),
    outcome_lesson_version_id: UUID | None = None,
    focus_roster: tuple[str, ...] = (),
    enforce_version_pin: bool = False,
) -> DirectionDecisionContext:
    """Compile bounded direction decision capsule from pinned state + prerequisites."""
    structured_lesson = outcome_lesson_version_id
    if structured_lesson is None and prerequisites is not None:
        structured_lesson = prerequisites.outcome_lesson_version_id
    legacy_lessons = () if structured_lesson is not None else decision_lessons
    return compile_direction_decision_context(
        DirectionDecisionContextCompileInput(
            loaded=loaded,
            prerequisites=prerequisites,
            attention_plan=attention_plan,
            analyst_payloads=analyst_payloads,
            deliberation_summaries=deliberation_summaries,
            shadow_calibrations=shadow_calibrations,
            calibrated_forecasts=calibrated_forecasts,
            prior_direction=prior_direction,
            decision_lessons=legacy_lessons,
            outcome_lesson_version_id=structured_lesson,
            focus_roster=focus_roster,
            enforce_version_pin=enforce_version_pin,
        )
    )


def compile_deliberation_role_context(
    *,
    loaded: LoadedResearchState,
    ticker: str,
    bundle: TickerEvidenceBundle,
    amendment: EvidenceBundleAmendment | None = None,
) -> tuple[ContextCapsule, ContextManifest]:
    """Compile bounded deliberation capsule (bundle/amendment evidence only)."""
    return compile_context_capsule(
        ContextCompileInput(
            role=ContextRole.DELIBERATION,
            state=loaded,
            ticker=ticker,
            bundle=bundle,
            amendment=amendment,
        )
    )


def _attach_outcome_lesson_linkage(
    phase_inputs: dict[str, Any],
    *,
    outcome_lesson_pin: dict[str, object] | None,
) -> dict[str, Any]:
    """Embed structured lesson pin for WP14 manifest telemetry."""
    if not isinstance(outcome_lesson_pin, dict):
        return phase_inputs
    lesson_id = outcome_lesson_pin.get("lesson_version_id")
    if lesson_id is None or not str(lesson_id).strip():
        return phase_inputs
    out = dict(phase_inputs)
    out["outcome_lesson_version_id"] = str(lesson_id)
    content_hash = outcome_lesson_pin.get("content_hash")
    if content_hash:
        out["outcome_lesson_content_hash"] = str(content_hash)
    return out


def _attach_manifest_linkage(
    phase_inputs: dict[str, Any],
    *,
    manifest: ContextManifest,
    capsule: ContextCapsule,
) -> dict[str, Any]:
    """Embed manifest/capsule linkage for WP1 prompt telemetry."""
    out = dict(phase_inputs)
    out["context_manifest_id"] = str(manifest.manifest_id)
    out["context_manifest_content_hash"] = manifest.content_hash
    out["context_capsule_id"] = str(capsule.capsule_id)
    out["context_capsule_content_hash"] = capsule.content_hash
    out["context_state_version_id"] = str(manifest.state_version_id)
    return out


def wire_analyst_phase_inputs(
    phase_inputs: dict[str, Any],
    *,
    ticker: str,
    bundle: TickerEvidenceBundle,
    research_state_pin: dict[str, object] | None,
    research_state_store: ResearchStateStore | None = None,
    outcome_lesson_pin: dict[str, object] | None = None,
    changed_evidence_ids: frozenset[UUID] | None = None,
) -> RoleContextWireResult:
    """Apply analyst context compiler wiring (shadow records; enforce replaces structured slice)."""
    mode = resolve_context_compiler_mode()
    if mode is ContextCompilerMode.OFF:
        return RoleContextWireResult(
            phase_inputs=dict(phase_inputs),
            capsule=None,
            manifest=None,
            mode=mode,
        )

    loaded = try_load_pinned_research_state(research_state_store, research_state_pin)
    if loaded is None:
        logger.debug("analyst context compile skipped — no pinned research state in store")
        return RoleContextWireResult(
            phase_inputs=dict(phase_inputs),
            capsule=None,
            manifest=None,
            mode=mode,
        )

    capsule, manifest = compile_analyst_role_context(
        loaded=loaded,
        ticker=ticker,
        bundle=bundle,
        changed_evidence_ids=changed_evidence_ids,
    )

    if mode is ContextCompilerMode.ENFORCE:
        out = strip_blinded_forbidden_keys(phase_inputs, role="analyst")
        out["structured_context"] = capsule.body
        out = _attach_manifest_linkage(out, manifest=manifest, capsule=capsule)
        out = _attach_outcome_lesson_linkage(out, outcome_lesson_pin=outcome_lesson_pin)
        assert_blinded_analyst_prompt(out)
        return RoleContextWireResult(
            phase_inputs=out,
            capsule=capsule,
            manifest=manifest,
            mode=mode,
        )

    out = dict(phase_inputs)
    out["context_capsule_shadow"] = capsule.model_dump(mode="json")
    out["context_manifest_shadow"] = manifest.model_dump(mode="json")
    out = _attach_manifest_linkage(out, manifest=manifest, capsule=capsule)
    out = _attach_outcome_lesson_linkage(out, outcome_lesson_pin=outcome_lesson_pin)
    return RoleContextWireResult(
        phase_inputs=out,
        capsule=capsule,
        manifest=manifest,
        mode=mode,
    )


def wire_deliberation_phase_inputs(
    phase_inputs: dict[str, Any],
    *,
    ticker: str,
    bundle: TickerEvidenceBundle | None,
    research_state_pin: dict[str, object] | None,
    research_state_store: ResearchStateStore | None = None,
    amendment: EvidenceBundleAmendment | None = None,
) -> RoleContextWireResult:
    """Apply deliberation context compiler wiring beside incumbent deliberation inputs."""
    mode = resolve_context_compiler_mode()
    if mode is ContextCompilerMode.OFF:
        return RoleContextWireResult(
            phase_inputs=dict(phase_inputs),
            capsule=None,
            manifest=None,
            mode=mode,
        )

    if bundle is None:
        logger.debug("deliberation context compile skipped — no base evidence bundle")
        return RoleContextWireResult(
            phase_inputs=dict(phase_inputs),
            capsule=None,
            manifest=None,
            mode=mode,
        )

    loaded = try_load_pinned_research_state(research_state_store, research_state_pin)
    if loaded is None:
        return RoleContextWireResult(
            phase_inputs=dict(phase_inputs),
            capsule=None,
            manifest=None,
            mode=mode,
        )

    capsule, manifest = compile_deliberation_role_context(
        loaded=loaded,
        ticker=ticker,
        bundle=bundle,
        amendment=amendment,
    )

    if mode is ContextCompilerMode.ENFORCE:
        out = strip_blinded_forbidden_keys(phase_inputs, role="deliberation")
        out.pop("base_evidence_bundle", None)
        out["structured_context"] = capsule.body
        out = _attach_manifest_linkage(out, manifest=manifest, capsule=capsule)
        assert_blinded_deliberation_prompt(out)
        return RoleContextWireResult(
            phase_inputs=out,
            capsule=capsule,
            manifest=manifest,
            mode=mode,
        )

    out = dict(phase_inputs)
    out["context_capsule_shadow"] = capsule.model_dump(mode="json")
    out["context_manifest_shadow"] = manifest.model_dump(mode="json")
    out = _attach_manifest_linkage(out, manifest=manifest, capsule=capsule)
    return RoleContextWireResult(
        phase_inputs=out,
        capsule=capsule,
        manifest=manifest,
        mode=mode,
    )


def _parse_direction_prerequisites(raw: dict[str, object] | None) -> DirectionPrerequisiteSnapshot | None:
    if not isinstance(raw, dict) or not raw:
        return None
    try:
        return DirectionPrerequisiteSnapshot.model_validate(raw)
    except Exception:
        logger.warning("invalid direction_prerequisite_snapshot; skipping direction context compile")
        return None


def wire_direction_phase_inputs(
    phase_inputs: dict[str, Any],
    *,
    research_state_pin: dict[str, object] | None,
    research_state_store: ResearchStateStore | None = None,
    direction_prerequisite_snapshot: dict[str, object] | None = None,
    outcome_lesson_pin: dict[str, object] | None = None,
    attention_plan: AttentionPlan | None = None,
    analyst_payloads: dict[str, dict[str, Any]] | None = None,
    deliberation_summaries: dict[str, dict[str, Any]] | None = None,
    shadow_calibrations: dict[str, dict[str, Any]] | None = None,
    calibrated_forecasts: dict[str, dict[str, Any]] | None = None,
    prior_direction: dict[str, Any] | None = None,
    decision_lessons: tuple[dict[str, Any], ...] = (),
    focus_roster: tuple[str, ...] = (),
) -> RoleContextWireResult:
    """Apply direction decision context compiler beside incumbent PM direction inputs."""
    mode = resolve_context_compiler_mode()
    if mode is ContextCompilerMode.OFF:
        return RoleContextWireResult(
            phase_inputs=dict(phase_inputs),
            capsule=None,
            manifest=None,
            mode=mode,
        )

    loaded = try_load_pinned_research_state(research_state_store, research_state_pin)
    if loaded is None:
        logger.debug("direction context compile skipped — no pinned research state in store")
        return RoleContextWireResult(
            phase_inputs=dict(phase_inputs),
            capsule=None,
            manifest=None,
            mode=mode,
        )

    prerequisites = _parse_direction_prerequisites(direction_prerequisite_snapshot)
    lesson_id: UUID | None = None
    if isinstance(outcome_lesson_pin, dict):
        raw_lesson = outcome_lesson_pin.get("lesson_version_id")
        if raw_lesson is not None:
            try:
                lesson_id = UUID(str(raw_lesson))
            except ValueError:
                lesson_id = None
    enforce_pin = mode is ContextCompilerMode.ENFORCE
    try:
        decision_ctx = compile_direction_role_context(
            loaded=loaded,
            prerequisites=prerequisites,
            attention_plan=attention_plan,
            analyst_payloads=analyst_payloads,
            deliberation_summaries=deliberation_summaries,
            shadow_calibrations=shadow_calibrations,
            calibrated_forecasts=calibrated_forecasts,
            prior_direction=prior_direction,
            decision_lessons=decision_lessons,
            outcome_lesson_version_id=lesson_id,
            focus_roster=focus_roster,
            enforce_version_pin=enforce_pin,
        )
    except ValueError:
        if enforce_pin:
            raise
        logger.debug("direction context compile skipped — prerequisite validation failed")
        return RoleContextWireResult(
            phase_inputs=dict(phase_inputs),
            capsule=None,
            manifest=None,
            mode=mode,
        )

    capsule = decision_ctx.base_capsule
    manifest = decision_ctx.base_manifest

    if mode is ContextCompilerMode.ENFORCE:
        out = strip_direction_weight_keys(dict(phase_inputs))
        out.pop("portfolio_performance", None)
        out["structured_context"] = decision_ctx.structured_body
        out = _attach_manifest_linkage(out, manifest=manifest, capsule=capsule)
        out = _attach_outcome_lesson_linkage(out, outcome_lesson_pin=outcome_lesson_pin)
        out["direction_decision_context_hash"] = decision_ctx.content_hash
        assert_direction_no_target_weights(out["structured_context"])
        return RoleContextWireResult(
            phase_inputs=out,
            capsule=capsule,
            manifest=manifest,
            mode=mode,
            direction_decision_context=decision_ctx,
        )

    out = dict(phase_inputs)
    out["context_capsule_shadow"] = capsule.model_dump(mode="json")
    out["context_manifest_shadow"] = manifest.model_dump(mode="json")
    out["direction_decision_context_shadow"] = decision_ctx.model_dump(mode="json")
    if prerequisites is None or prerequisites.state_version_id is None:
        out["direction_context_degraded"] = "missing_versioned_prerequisites"
    out = _attach_manifest_linkage(out, manifest=manifest, capsule=capsule)
    out = _attach_outcome_lesson_linkage(out, outcome_lesson_pin=outcome_lesson_pin)
    return RoleContextWireResult(
        phase_inputs=out,
        capsule=capsule,
        manifest=manifest,
        mode=mode,
        direction_decision_context=decision_ctx,
    )


__all__ = [
    "ContextCompilerMode",
    "DIGIQUANT_CONTEXT_COMPILER_MODE_ENV",
    "RoleContextWireResult",
    "changed_evidence_ids_from_bundle",
    "compile_analyst_role_context",
    "compile_deliberation_role_context",
    "compile_direction_role_context",
    "resolve_context_compiler_mode",
    "try_load_pinned_research_state",
    "wire_analyst_phase_inputs",
    "wire_deliberation_phase_inputs",
    "wire_direction_phase_inputs",
]
