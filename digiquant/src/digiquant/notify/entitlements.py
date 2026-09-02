"""digiquant plan-tier → artifact-class entitlement map (Kairos tenancy T5 mirror).

Spec §5-T5 matrix as amended by ``docs/agent-backlog/kairos-tenancy/PRICING.md``:
Observer (free) teaser; Brief (weights/NAV); Desk (glass-box + paper brokers);
Studio (overlay / private book / BYOK). Enterprise matches Studio for content.

TypeScript mirror (T5 UI gate) MUST stay in sync:
  frontend/dashboard/lib/entitlements.ts
When either file changes the matrix, update the other in the same PR.
"""

from __future__ import annotations

from enum import StrEnum
from typing import Final


# String-match ``workspaces.plan_tier`` DB enum (migration 115).
class PlanTier(StrEnum):
    FREE = "free"
    BRIEF = "brief"
    DESK = "desk"
    STUDIO = "studio"
    ENTERPRISE = "enterprise"


class ArtifactClass(StrEnum):
    """Artifact classes gated by plan tier (spec §5-T5 + Brief/Desk/Studio)."""

    RESEARCH = "research"
    NARRATIVE = "narrative"
    DIGEST_SUMMARY = "digest_summary"
    PORTFOLIO_TEASER = "portfolio_teaser"
    HOUSE_WEIGHTS_NAV = "house_weights_nav"
    GLASSBOX_ECONOMICS = "glassbox_economics"
    PRIVATE_BOOK = "private_book"
    BROKER_STATUS = "broker_status"
    OVERLAY_PROFILE = "overlay_profile"


PLAN_TIERS: Final[tuple[PlanTier, ...]] = (
    PlanTier.FREE,
    PlanTier.BRIEF,
    PlanTier.DESK,
    PlanTier.STUDIO,
    PlanTier.ENTERPRISE,
)

OBSERVER_CLASSES: Final[frozenset[ArtifactClass]] = frozenset(
    {
        ArtifactClass.RESEARCH,
        ArtifactClass.NARRATIVE,
        ArtifactClass.DIGEST_SUMMARY,
        ArtifactClass.PORTFOLIO_TEASER,
    }
)

BRIEF_CLASSES: Final[frozenset[ArtifactClass]] = OBSERVER_CLASSES | frozenset(
    {ArtifactClass.HOUSE_WEIGHTS_NAV}
)

DESK_CLASSES: Final[frozenset[ArtifactClass]] = BRIEF_CLASSES | frozenset(
    {ArtifactClass.GLASSBOX_ECONOMICS, ArtifactClass.BROKER_STATUS}
)

STUDIO_CLASSES: Final[frozenset[ArtifactClass]] = DESK_CLASSES | frozenset(
    {ArtifactClass.PRIVATE_BOOK, ArtifactClass.OVERLAY_PROFILE}
)

ALLOWED: Final[dict[PlanTier, frozenset[ArtifactClass]]] = {
    PlanTier.FREE: OBSERVER_CLASSES,
    PlanTier.BRIEF: BRIEF_CLASSES,
    PlanTier.DESK: DESK_CLASSES,
    PlanTier.STUDIO: STUDIO_CLASSES,
    PlanTier.ENTERPRISE: STUDIO_CLASSES,
}

ARTIFACT_CLASSES: Final[tuple[ArtifactClass, ...]] = tuple(ArtifactClass)

_TIER_RANK: Final[dict[PlanTier, int]] = {
    PlanTier.FREE: 0,
    PlanTier.BRIEF: 1,
    PlanTier.DESK: 2,
    PlanTier.STUDIO: 3,
    PlanTier.ENTERPRISE: 4,
}


def is_plan_tier(value: object) -> bool:
    if not isinstance(value, str):
        return False
    return value in {t.value for t in PLAN_TIERS}


def max_plan_tier(a: PlanTier, b: PlanTier | None) -> PlanTier:
    """Higher of two plan tiers (creator/ops plan_floor elevation)."""
    if b is None:
        return a
    return a if _TIER_RANK[a] >= _TIER_RANK[b] else b


def can(tier: PlanTier, artifact_class: ArtifactClass) -> bool:
    """Whether ``tier`` may see ``artifact_class`` (presentation filter — RLS is hard gate)."""
    return artifact_class in ALLOWED[tier]


def required_tier_for(artifact_class: ArtifactClass) -> PlanTier:
    """Minimum tier that unlocks a class — for locked-state upgrade copy."""
    if artifact_class in OBSERVER_CLASSES:
        return PlanTier.FREE
    if artifact_class is ArtifactClass.HOUSE_WEIGHTS_NAV:
        return PlanTier.BRIEF
    if artifact_class in {ArtifactClass.GLASSBOX_ECONOMICS, ArtifactClass.BROKER_STATUS}:
        return PlanTier.DESK
    return PlanTier.STUDIO


__all__ = [
    "ARTIFACT_CLASSES",
    "ALLOWED",
    "ArtifactClass",
    "BRIEF_CLASSES",
    "DESK_CLASSES",
    "OBSERVER_CLASSES",
    "PLAN_TIERS",
    "PlanTier",
    "STUDIO_CLASSES",
    "can",
    "is_plan_tier",
    "max_plan_tier",
    "required_tier_for",
]
