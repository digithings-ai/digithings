"""WP14.3 — typed H7 decision context sections after prerequisite gates (#2946).

Compiles mandate, calibration, contribution/cost, pre-trade risk, prior
authorization, and forecast feedback sections from versioned inputs. H7 authority
limits are preserved — no target weights and no numerical forecast mutation.
"""

from __future__ import annotations

import json
from dataclasses import dataclass
from enum import StrEnum
from typing import Any  # score:allow untyped any — scored-lint: heterogeneous dict / client shapes
from uuid import UUID

from pydantic import Field, model_validator

from digiquant.olympus.research_retrieval.context import (
    ContextCapsule,
    ContextCompileInput,
    ContextManifest,
    ContextRole,
    compile_context_capsule,
)
from digiquant.olympus.research_retrieval.models import (
    NonEmptyStr,
    ResearchStateModel,
    content_digest,
)
from digiquant.olympus.research_retrieval.planner import AttentionPlan
from digiquant.olympus.research_retrieval.store import LoadedResearchState

H7_SECTION_SCHEMA_VERSION: int = 1

_H7_WEIGHT_FORBIDDEN_KEYS = frozenset(
    {
        "target_pct",
        "target_weight",
        "target_weight_pct",
        "recommended_weight_pct",
        "recommended_weight",
        "weights",
        "allocation_weights",
    }
)


class H7SectionKind(StrEnum):
    """Typed H7 decision context sections."""

    MANDATE = "mandate"
    CALIBRATION = "calibration"
    CONTRIBUTION_COST = "contribution_cost"
    PRE_TRADE_RISK = "pre_trade_risk"
    PRIOR_AUTHORIZATION = "prior_authorization"
    UNRESOLVED_FORECASTS = "unresolved_forecasts"
    MATURED_FORECASTS = "matured_forecasts"


class H7SectionAvailability(StrEnum):
    """Whether a section carries versioned entity IDs."""

    AVAILABLE = "available"
    UNAVAILABLE = "unavailable"
    DEGRADED = "degraded"


class H7PrerequisiteSnapshot(ResearchStateModel):
    """Versioned WP3/WP5/WP9 inputs pinned at preflight for H7 compile."""

    state_version_id: UUID | None = None
    accounting_period_id: UUID | None = None
    accounting_period_content_hash: NonEmptyStr | None = None
    matured_forecast_outcome_ids: tuple[NonEmptyStr, ...] = Field(default_factory=tuple)
    unresolved_forecast_effective_ids: tuple[NonEmptyStr, ...] = Field(default_factory=tuple)
    ex_ante_risk_snapshot_hash: NonEmptyStr | None = None
    action_cost_estimate_ids: tuple[NonEmptyStr, ...] = Field(default_factory=tuple)
    outcome_lesson_version_id: UUID | None = None
    outcome_lesson_content_hash: NonEmptyStr | None = None
    schema_version: int = H7_SECTION_SCHEMA_VERSION


class H7ContextSection(ResearchStateModel):
    """One typed H7 context section — versioned IDs or explicit unavailability."""

    kind: H7SectionKind
    availability: H7SectionAvailability
    entity_ids: tuple[NonEmptyStr, ...] = Field(default_factory=tuple)
    content_hash: NonEmptyStr | None = None
    unavailable_reason: NonEmptyStr | None = None
    degraded_reason: NonEmptyStr | None = None
    schema_version: int = H7_SECTION_SCHEMA_VERSION

    @model_validator(mode="after")
    def _validate_availability(self) -> H7ContextSection:
        if self.availability is H7SectionAvailability.AVAILABLE:
            if not self.entity_ids and self.content_hash is None:
                raise ValueError("available section requires entity_ids or content_hash")
        if self.availability is H7SectionAvailability.UNAVAILABLE and not self.unavailable_reason:
            raise ValueError("unavailable section requires unavailable_reason")
        if self.availability is H7SectionAvailability.DEGRADED and not self.degraded_reason:
            raise ValueError("degraded section requires degraded_reason")
        return self


class H7DecisionContext(ResearchStateModel):
    """Compiled H7 decision capsule: role context + typed sections."""

    sections: tuple[H7ContextSection, ...]
    base_capsule: ContextCapsule
    base_manifest: ContextManifest
    content_hash: NonEmptyStr
    schema_version: int = H7_SECTION_SCHEMA_VERSION

    @property
    def structured_body(self) -> str:
        """JSONL body for provider ``structured_context`` injection."""
        lines: list[str] = []
        lines.append(json.dumps({"role": ContextRole.H7_PM.value, "sections": len(self.sections)}))
        lines.append(self.base_capsule.body)
        for section in self.sections:
            lines.append(section.model_dump_json())
        return "\n".join(lines)


@dataclass(frozen=True)
class H7DecisionContextCompileInput:
    """Inputs for one H7 decision context compile."""

    loaded: LoadedResearchState
    prerequisites: H7PrerequisiteSnapshot | None
    attention_plan: AttentionPlan | None = None
    analyst_payloads: dict[str, dict[str, Any]] | None = None
    deliberation_summaries: dict[str, dict[str, Any]] | None = None
    shadow_calibrations: dict[str, dict[str, Any]] | None = None
    calibrated_forecasts: dict[str, dict[str, Any]] | None = None
    prior_direction: dict[str, Any] | None = None
    decision_lessons: tuple[dict[str, Any], ...] = ()
    outcome_lesson_version_id: UUID | None = None
    focus_roster: tuple[str, ...] = ()
    enforce_version_pin: bool = False


def _section_content_hash(kind: H7SectionKind, entity_ids: tuple[str, ...]) -> str:
    return content_digest({"kind": kind.value, "entity_ids": list(entity_ids)})


def _mandate_entity_ids(
    *,
    analyst_payloads: dict[str, dict[str, Any]],
    deliberation_summaries: dict[str, dict[str, Any]],
    focus_roster: tuple[str, ...],
) -> tuple[str, ...]:
    ids: set[str] = set()
    roster = focus_roster or tuple(analyst_payloads.keys())
    for ticker in sorted(roster):
        ids.add(f"analyst:{ticker.strip().upper()}")
    for ticker, summary in sorted(deliberation_summaries.items()):
        if not isinstance(summary, dict):
            continue
        eff = summary.get("effective_forecast_id")
        if eff:
            ids.add(f"effective_forecast:{eff}")
        base = summary.get("base_forecast_id")
        if base:
            ids.add(f"base_forecast:{base}")
    return tuple(sorted(ids))


def _calibration_entity_ids(
    *,
    shadow_calibrations: dict[str, dict[str, Any]],
    calibrated_forecasts: dict[str, dict[str, Any]],
) -> tuple[str, ...]:
    ids: set[str] = set()
    for cal_id in sorted(shadow_calibrations):
        ids.add(f"forecast_calibration:{cal_id}")
    for ticker in sorted(calibrated_forecasts):
        payload = calibrated_forecasts[ticker]
        if isinstance(payload, dict):
            cf_id = payload.get("calibrated_forecast_id") or payload.get("id")
            if cf_id:
                ids.add(f"calibrated_forecast:{cf_id}")
            else:
                ids.add(f"calibrated_forecast_ticker:{ticker}")
    return tuple(sorted(ids))


def _prior_authorization_entity_ids(
    *,
    prior_direction: dict[str, Any],
    decision_lessons: tuple[dict[str, Any], ...],
    outcome_lesson_version_id: UUID | None = None,
) -> tuple[str, ...]:
    ids: set[str] = set()
    if outcome_lesson_version_id is not None:
        ids.add(f"outcome_lesson:{outcome_lesson_version_id}")
        return tuple(sorted(ids))
    if prior_direction:
        memo_date = prior_direction.get("date")
        if memo_date:
            ids.add(f"prior_pm_memo:{memo_date}")
    for idx, lesson in enumerate(decision_lessons):
        if not isinstance(lesson, dict):
            continue
        decision_id = lesson.get("decision_id") or lesson.get("id")
        if decision_id:
            ids.add(f"decision_lesson:{decision_id}")
        else:
            ids.add(f"decision_lesson_index:{idx}")
    return tuple(sorted(ids))


def _build_section(
    kind: H7SectionKind,
    *,
    entity_ids: tuple[str, ...],
    degraded_reason: str | None = None,
    unavailable_reason: str | None = None,
) -> H7ContextSection:
    if unavailable_reason:
        return H7ContextSection(
            kind=kind,
            availability=H7SectionAvailability.UNAVAILABLE,
            unavailable_reason=unavailable_reason,
        )
    if not entity_ids:
        return H7ContextSection(
            kind=kind,
            availability=H7SectionAvailability.UNAVAILABLE,
            unavailable_reason=f"{kind.value}_inputs_missing",
        )
    availability = (
        H7SectionAvailability.DEGRADED if degraded_reason else H7SectionAvailability.AVAILABLE
    )
    digest = _section_content_hash(kind, entity_ids)
    return H7ContextSection(
        kind=kind,
        availability=availability,
        entity_ids=entity_ids,
        content_hash=digest,
        degraded_reason=degraded_reason,
    )


def _require_pinned_prerequisites(
    *,
    loaded: LoadedResearchState,
    prerequisites: H7PrerequisiteSnapshot | None,
) -> H7PrerequisiteSnapshot:
    if prerequisites is None:
        raise ValueError("H7 enforce requires versioned h7_prerequisite_snapshot")
    pin_id = prerequisites.state_version_id
    if pin_id is None:
        raise ValueError("H7 enforce requires prerequisites.state_version_id")
    if pin_id != loaded.version.state_version_id:
        raise ValueError("prerequisites.state_version_id must match pinned research state")
    return prerequisites


def compile_h7_decision_context(inp: H7DecisionContextCompileInput) -> H7DecisionContext:
    """Compile H7 decision context from pinned state + prerequisite snapshot."""
    prerequisites = inp.prerequisites
    if inp.enforce_version_pin:
        prerequisites = _require_pinned_prerequisites(
            loaded=inp.loaded, prerequisites=prerequisites
        )

    base_capsule, base_manifest = compile_context_capsule(
        ContextCompileInput(
            role=ContextRole.H7_PM,
            state=inp.loaded,
            attention_plan=inp.attention_plan,
        )
    )

    analyst = dict(inp.analyst_payloads or {})
    deliberation = dict(inp.deliberation_summaries or {})
    calibrations = dict(inp.shadow_calibrations or {})
    calibrated = dict(inp.calibrated_forecasts or {})
    prior = dict(inp.prior_direction or {})

    mandate_ids = _mandate_entity_ids(
        analyst_payloads=analyst,
        deliberation_summaries=deliberation,
        focus_roster=inp.focus_roster,
    )
    mandate = _build_section(H7SectionKind.MANDATE, entity_ids=mandate_ids)

    cal_ids = _calibration_entity_ids(
        shadow_calibrations=calibrations,
        calibrated_forecasts=calibrated,
    )
    calibration = _build_section(
        H7SectionKind.CALIBRATION,
        entity_ids=cal_ids,
        degraded_reason="shadow_calibration_observational" if cal_ids else None,
        unavailable_reason=None if cal_ids else None,
    )

    contrib_ids: tuple[str, ...] = ()
    cost_ids: tuple[str, ...] = ()
    if prerequisites is not None:
        if prerequisites.accounting_period_id is not None:
            contrib_ids = (f"accounting_period:{prerequisites.accounting_period_id}",)
        cost_ids = tuple(
            f"action_cost_estimate:{eid}" for eid in prerequisites.action_cost_estimate_ids
        )
    contribution_cost_ids = tuple(sorted(set(contrib_ids) | set(cost_ids)))
    contribution_cost = _build_section(
        H7SectionKind.CONTRIBUTION_COST,
        entity_ids=contribution_cost_ids,
    )

    risk_hash = prerequisites.ex_ante_risk_snapshot_hash if prerequisites else None
    if risk_hash:
        pre_trade_risk = _build_section(
            H7SectionKind.PRE_TRADE_RISK,
            entity_ids=(f"ex_ante_risk_snapshot:{risk_hash}",),
        )
    else:
        pre_trade_risk = H7ContextSection(
            kind=H7SectionKind.PRE_TRADE_RISK,
            availability=H7SectionAvailability.UNAVAILABLE,
            unavailable_reason="pre_trade_risk_report_not_yet_built_at_h7",
        )

    auth_ids = _prior_authorization_entity_ids(
        prior_direction=prior,
        decision_lessons=inp.decision_lessons,
        outcome_lesson_version_id=(
            inp.outcome_lesson_version_id
            if inp.outcome_lesson_version_id is not None
            else (
                prerequisites.outcome_lesson_version_id if prerequisites is not None else None
            )
        ),
    )
    prior_auth = _build_section(H7SectionKind.PRIOR_AUTHORIZATION, entity_ids=auth_ids)

    matured_ids = tuple(
        f"forecast_outcome:{oid}"
        for oid in (prerequisites.matured_forecast_outcome_ids if prerequisites else ())
    )
    matured = _build_section(H7SectionKind.MATURED_FORECASTS, entity_ids=matured_ids)

    unresolved_ids = tuple(
        f"effective_forecast:{eid}"
        for eid in (prerequisites.unresolved_forecast_effective_ids if prerequisites else ())
    )
    unresolved = _build_section(H7SectionKind.UNRESOLVED_FORECASTS, entity_ids=unresolved_ids)

    sections = (
        mandate,
        calibration,
        contribution_cost,
        pre_trade_risk,
        prior_auth,
        unresolved,
        matured,
    )
    digest = content_digest(
        {
            "base_manifest": base_manifest.content_hash,
            "sections": [section.model_dump(mode="json") for section in sections],
        }
    )
    ctx = H7DecisionContext(
        sections=sections,
        base_capsule=base_capsule,
        base_manifest=base_manifest,
        content_hash=digest,
    )
    assert_h7_no_target_weights(ctx.structured_body)
    return ctx


def strip_h7_weight_keys(payload: dict[str, Any]) -> dict[str, Any]:
    """Remove target-weight fields from H7 provider inputs."""
    return {key: value for key, value in payload.items() if key not in _H7_WEIGHT_FORBIDDEN_KEYS}


def assert_h7_no_target_weights(text: str) -> None:
    """Hard guard: H7 structured context must not carry target allocation weights."""
    lowered = text.lower()
    for key in _H7_WEIGHT_FORBIDDEN_KEYS:
        if key in lowered:
            raise ValueError(f"H7 context must not include target weight key {key!r}")


__all__ = [
    "H7DecisionContext",
    "H7DecisionContextCompileInput",
    "H7ContextSection",
    "H7PrerequisiteSnapshot",
    "H7SectionAvailability",
    "H7SectionKind",
    "H7_SECTION_SCHEMA_VERSION",
    "assert_h7_no_target_weights",
    "compile_h7_decision_context",
    "strip_h7_weight_keys",
]
