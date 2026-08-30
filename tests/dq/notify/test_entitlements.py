"""Pin T5 entitlement matrix (+ free-teaser classes) against the Python mirror."""

from __future__ import annotations

import pytest

from digiquant.notify.entitlements import (
    ARTIFACT_CLASSES,
    PLAN_TIERS,
    ArtifactClass,
    PlanTier,
    can,
    max_plan_tier,
    required_tier_for,
)

_MATRIX: dict[PlanTier, dict[ArtifactClass, bool]] = {
    PlanTier.FREE: {
        ArtifactClass.RESEARCH: True,
        ArtifactClass.NARRATIVE: True,
        ArtifactClass.DIGEST_SUMMARY: True,
        ArtifactClass.PORTFOLIO_TEASER: True,
        ArtifactClass.HOUSE_WEIGHTS_NAV: False,
        ArtifactClass.GLASSBOX_ECONOMICS: False,
        ArtifactClass.PRIVATE_BOOK: False,
        ArtifactClass.BROKER_STATUS: False,
        ArtifactClass.OVERLAY_PROFILE: False,
    },
    PlanTier.BASELINE: {
        ArtifactClass.RESEARCH: True,
        ArtifactClass.NARRATIVE: True,
        ArtifactClass.DIGEST_SUMMARY: True,
        ArtifactClass.PORTFOLIO_TEASER: True,
        ArtifactClass.HOUSE_WEIGHTS_NAV: True,
        ArtifactClass.GLASSBOX_ECONOMICS: True,
        ArtifactClass.PRIVATE_BOOK: False,
        ArtifactClass.BROKER_STATUS: False,
        ArtifactClass.OVERLAY_PROFILE: False,
    },
    PlanTier.CUSTOM: {cls: True for cls in ArtifactClass},
    PlanTier.ENTERPRISE: {cls: True for cls in ArtifactClass},
}


@pytest.mark.unit
@pytest.mark.parametrize("tier", list(PlanTier))
@pytest.mark.parametrize("artifact_class", list(ArtifactClass))
def test_can_matches_t5_matrix(tier: PlanTier, artifact_class: ArtifactClass) -> None:
    assert can(tier, artifact_class) == _MATRIX[tier][artifact_class]


@pytest.mark.unit
def test_matrix_cardinality() -> None:
    assert len(PLAN_TIERS) == 4
    assert len(ARTIFACT_CLASSES) == 9
    assert len(PLAN_TIERS) * len(ARTIFACT_CLASSES) == 36


@pytest.mark.unit
def test_required_tier_for() -> None:
    assert required_tier_for(ArtifactClass.RESEARCH) == PlanTier.FREE
    assert required_tier_for(ArtifactClass.NARRATIVE) == PlanTier.FREE
    assert required_tier_for(ArtifactClass.DIGEST_SUMMARY) == PlanTier.FREE
    assert required_tier_for(ArtifactClass.PORTFOLIO_TEASER) == PlanTier.FREE
    assert required_tier_for(ArtifactClass.HOUSE_WEIGHTS_NAV) == PlanTier.BASELINE
    assert required_tier_for(ArtifactClass.GLASSBOX_ECONOMICS) == PlanTier.BASELINE
    assert required_tier_for(ArtifactClass.PRIVATE_BOOK) == PlanTier.CUSTOM
    assert required_tier_for(ArtifactClass.BROKER_STATUS) == PlanTier.CUSTOM
    assert required_tier_for(ArtifactClass.OVERLAY_PROFILE) == PlanTier.CUSTOM


@pytest.mark.unit
def test_max_plan_tier_elevates_creator_floor() -> None:
    assert max_plan_tier(PlanTier.FREE, PlanTier.CUSTOM) == PlanTier.CUSTOM
    assert max_plan_tier(PlanTier.BASELINE, None) == PlanTier.BASELINE
    assert max_plan_tier(PlanTier.CUSTOM, PlanTier.BASELINE) == PlanTier.CUSTOM
