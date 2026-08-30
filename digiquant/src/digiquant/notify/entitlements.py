"""Olympus plan-tier → artifact-class entitlement map (Kairos tenancy T5 mirror).

Spec §5-T5 matrix is the single source of truth — pin it in entitlements tests.

TypeScript mirror (T5 UI gate) MUST stay in sync:
  frontend/olympus/lib/entitlements.ts
When either file changes the matrix, update the other in the same PR.
"""

from __future__ import annotations

from enum import StrEnum
from typing import Final


# String-match ``workspaces.plan_tier`` DB enum.
class PlanTier(StrEnum):
    FREE = "free"
    BASELINE = "baseline"
    CUSTOM = "custom"
    ENTERPRISE = "enterprise"


class ArtifactClass(StrEnum):
    """Artifact classes gated by plan tier (spec §5-T5)."""

    RESEARCH = "research"
    NARRATIVE = "narrative"
    HOUSE_WEIGHTS_NAV = "house_weights_nav"
    GLASSBOX_ECONOMICS = "glassbox_economics"
    PRIVATE_BOOK = "private_book"
    BROKER_STATUS = "broker_status"
    OVERLAY_PROFILE = "overlay_profile"


PLAN_TIERS: Final[tuple[PlanTier, ...]] = (
    PlanTier.FREE,
    PlanTier.BASELINE,
    PlanTier.CUSTOM,
    PlanTier.ENTERPRISE,
)

OBSERVER_CLASSES: Final[frozenset[ArtifactClass]] = frozenset(
    {ArtifactClass.RESEARCH, ArtifactClass.NARRATIVE}
)

BASELINE_CLASSES: Final[frozenset[ArtifactClass]] = OBSERVER_CLASSES | frozenset(
    {ArtifactClass.HOUSE_WEIGHTS_NAV, ArtifactClass.GLASSBOX_ECONOMICS}
)

CUSTOM_CLASSES: Final[frozenset[ArtifactClass]] = BASELINE_CLASSES | frozenset(
    {
        ArtifactClass.PRIVATE_BOOK,
        ArtifactClass.BROKER_STATUS,
        ArtifactClass.OVERLAY_PROFILE,
    }
)

ALLOWED: Final[dict[PlanTier, frozenset[ArtifactClass]]] = {
    PlanTier.FREE: OBSERVER_CLASSES,
    PlanTier.BASELINE: BASELINE_CLASSES,
    PlanTier.CUSTOM: CUSTOM_CLASSES,
    PlanTier.ENTERPRISE: CUSTOM_CLASSES,
}

ARTIFACT_CLASSES: Final[tuple[ArtifactClass, ...]] = tuple(ArtifactClass)


def is_plan_tier(value: object) -> bool:
    if not isinstance(value, str):
        return False
    return value in {t.value for t in PLAN_TIERS}


def can(tier: PlanTier, artifact_class: ArtifactClass) -> bool:
    """Whether ``tier`` may see ``artifact_class`` (presentation filter — RLS is hard gate)."""
    return artifact_class in ALLOWED[tier]


def required_tier_for(artifact_class: ArtifactClass) -> PlanTier:
    """Minimum tier that unlocks a class — for locked-state upgrade copy."""
    if artifact_class in OBSERVER_CLASSES:
        return PlanTier.FREE
    if artifact_class in {
        ArtifactClass.HOUSE_WEIGHTS_NAV,
        ArtifactClass.GLASSBOX_ECONOMICS,
    }:
        return PlanTier.BASELINE
    return PlanTier.CUSTOM


__all__ = [
    "ARTIFACT_CLASSES",
    "ALLOWED",
    "ArtifactClass",
    "BASELINE_CLASSES",
    "CUSTOM_CLASSES",
    "OBSERVER_CLASSES",
    "PLAN_TIERS",
    "PlanTier",
    "can",
    "is_plan_tier",
    "required_tier_for",
]
