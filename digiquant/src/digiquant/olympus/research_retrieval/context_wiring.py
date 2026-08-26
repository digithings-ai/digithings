"""WP14.2 — wire blinded H5/H6 context capsules into provider phase_inputs."""

from __future__ import annotations

import logging
import os
from dataclasses import dataclass
from enum import StrEnum
from typing import Any
from uuid import UUID

from digiquant.olympus.research_retrieval.blinding import (
    assert_blinded_h5_prompt,
    assert_blinded_h6_prompt,
    strip_blinded_forbidden_keys,
)
from digiquant.olympus.research_retrieval.context import (
    ContextCapsule,
    ContextCompileInput,
    ContextManifest,
    ContextRole,
    compile_context_capsule,
)
from digiquant.olympus.research_retrieval.models import (
    EvidenceBundleAmendment,
    TickerEvidenceBundle,
)
from digiquant.olympus.research_retrieval.store import (
    LoadedResearchState,
    ResearchStateMissingError,
    ResearchStateStore,
)

logger = logging.getLogger(__name__)

OLYMPUS_CONTEXT_COMPILER_MODE_ENV = "OLYMPUS_CONTEXT_COMPILER_MODE"


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


def resolve_context_compiler_mode() -> ContextCompilerMode:
    """Read ``OLYMPUS_CONTEXT_COMPILER_MODE``; unknown values → shadow."""
    raw = os.environ.get(OLYMPUS_CONTEXT_COMPILER_MODE_ENV, "shadow").strip().lower()
    try:
        return ContextCompilerMode(raw)
    except ValueError:
        logger.warning(
            "invalid %s=%r; using shadow (allowed: off|shadow|enforce)",
            OLYMPUS_CONTEXT_COMPILER_MODE_ENV,
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
    """Default H5 delta set: evidence IDs referenced by the pinned bundle."""
    return frozenset(bundle.evidence_ids)


def compile_h5_role_context(
    *,
    loaded: LoadedResearchState,
    ticker: str,
    bundle: TickerEvidenceBundle,
    changed_evidence_ids: frozenset[UUID] | None = None,
) -> tuple[ContextCapsule, ContextManifest]:
    """Compile bounded H5 capsule from pinned state + bundle."""
    delta = changed_evidence_ids or changed_evidence_ids_from_bundle(bundle)
    return compile_context_capsule(
        ContextCompileInput(
            role=ContextRole.H5_ANALYST,
            state=loaded,
            ticker=ticker,
            bundle=bundle,
            changed_evidence_ids=delta,
        )
    )


def compile_h6_role_context(
    *,
    loaded: LoadedResearchState,
    ticker: str,
    bundle: TickerEvidenceBundle,
    amendment: EvidenceBundleAmendment | None = None,
) -> tuple[ContextCapsule, ContextManifest]:
    """Compile bounded H6 capsule (bundle/amendment evidence only)."""
    return compile_context_capsule(
        ContextCompileInput(
            role=ContextRole.H6_DELIBERATION,
            state=loaded,
            ticker=ticker,
            bundle=bundle,
            amendment=amendment,
        )
    )


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


def wire_h5_phase_inputs(
    phase_inputs: dict[str, Any],
    *,
    ticker: str,
    bundle: TickerEvidenceBundle,
    research_state_pin: dict[str, object] | None,
    research_state_store: ResearchStateStore | None = None,
    changed_evidence_ids: frozenset[UUID] | None = None,
) -> RoleContextWireResult:
    """Apply H5 context compiler wiring (shadow records; enforce replaces structured slice)."""
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
        logger.debug("H5 context compile skipped — no pinned research state in store")
        return RoleContextWireResult(
            phase_inputs=dict(phase_inputs),
            capsule=None,
            manifest=None,
            mode=mode,
        )

    capsule, manifest = compile_h5_role_context(
        loaded=loaded,
        ticker=ticker,
        bundle=bundle,
        changed_evidence_ids=changed_evidence_ids,
    )

    if mode is ContextCompilerMode.ENFORCE:
        out = strip_blinded_forbidden_keys(phase_inputs, role="h5_analyst")
        out["structured_context"] = capsule.body
        out = _attach_manifest_linkage(out, manifest=manifest, capsule=capsule)
        assert_blinded_h5_prompt(out)
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


def wire_h6_phase_inputs(
    phase_inputs: dict[str, Any],
    *,
    ticker: str,
    bundle: TickerEvidenceBundle | None,
    research_state_pin: dict[str, object] | None,
    research_state_store: ResearchStateStore | None = None,
    amendment: EvidenceBundleAmendment | None = None,
) -> RoleContextWireResult:
    """Apply H6 context compiler wiring beside incumbent deliberation inputs."""
    mode = resolve_context_compiler_mode()
    if mode is ContextCompilerMode.OFF:
        return RoleContextWireResult(
            phase_inputs=dict(phase_inputs),
            capsule=None,
            manifest=None,
            mode=mode,
        )

    if bundle is None:
        logger.debug("H6 context compile skipped — no base evidence bundle")
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

    capsule, manifest = compile_h6_role_context(
        loaded=loaded,
        ticker=ticker,
        bundle=bundle,
        amendment=amendment,
    )

    if mode is ContextCompilerMode.ENFORCE:
        out = strip_blinded_forbidden_keys(phase_inputs, role="h6_deliberation")
        out.pop("base_evidence_bundle", None)
        out["structured_context"] = capsule.body
        out = _attach_manifest_linkage(out, manifest=manifest, capsule=capsule)
        assert_blinded_h6_prompt(out)
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


__all__ = [
    "ContextCompilerMode",
    "OLYMPUS_CONTEXT_COMPILER_MODE_ENV",
    "RoleContextWireResult",
    "changed_evidence_ids_from_bundle",
    "compile_h5_role_context",
    "compile_h6_role_context",
    "resolve_context_compiler_mode",
    "try_load_pinned_research_state",
    "wire_h5_phase_inputs",
    "wire_h6_phase_inputs",
]
