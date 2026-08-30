"""Entitlement matrix pins — must match frontend/olympus/lib/entitlements.ts (T5)."""

from __future__ import annotations

import pytest
from digiquant.notify.entitlements import (
    ALLOWED,
    ARTIFACT_CLASSES,
    ArtifactClass,
    PlanTier,
    can,
    required_tier_for,
)

pytestmark = pytest.mark.unit

# Spec §5-T5 matrix (Observer / Baseline / Custom columns).
_MATRIX: dict[PlanTier, dict[ArtifactClass, bool]] = {
    PlanTier.FREE: {
        ArtifactClass.RESEARCH: True,
        ArtifactClass.NARRATIVE: True,
        ArtifactClass.HOUSE_WEIGHTS_NAV: False,
        ArtifactClass.GLASSBOX_ECONOMICS: False,
        ArtifactClass.PRIVATE_BOOK: False,
        ArtifactClass.BROKER_STATUS: False,
        ArtifactClass.OVERLAY_PROFILE: False,
    },
    PlanTier.BASELINE: {
        ArtifactClass.RESEARCH: True,
        ArtifactClass.NARRATIVE: True,
        ArtifactClass.HOUSE_WEIGHTS_NAV: True,
        ArtifactClass.GLASSBOX_ECONOMICS: True,
        ArtifactClass.PRIVATE_BOOK: False,
        ArtifactClass.BROKER_STATUS: False,
        ArtifactClass.OVERLAY_PROFILE: False,
    },
    PlanTier.CUSTOM: {cls: True for cls in ArtifactClass},
    PlanTier.ENTERPRISE: {cls: True for cls in ArtifactClass},
}


@pytest.mark.parametrize("tier", list(PlanTier))
@pytest.mark.parametrize("artifact_class", list(ArtifactClass))
def test_can_matches_t5_matrix(tier: PlanTier, artifact_class: ArtifactClass) -> None:
    assert can(tier, artifact_class) == _MATRIX[tier][artifact_class]


def test_artifact_class_count() -> None:
    assert len(ARTIFACT_CLASSES) == 7


def test_required_tier_for_observer_classes() -> None:
    assert required_tier_for(ArtifactClass.RESEARCH) == PlanTier.FREE
    assert required_tier_for(ArtifactClass.NARRATIVE) == PlanTier.FREE


def test_required_tier_for_baseline_classes() -> None:
    assert required_tier_for(ArtifactClass.HOUSE_WEIGHTS_NAV) == PlanTier.BASELINE
    assert required_tier_for(ArtifactClass.GLASSBOX_ECONOMICS) == PlanTier.BASELINE


def test_required_tier_for_custom_classes() -> None:
    assert required_tier_for(ArtifactClass.PRIVATE_BOOK) == PlanTier.CUSTOM
    assert required_tier_for(ArtifactClass.BROKER_STATUS) == PlanTier.CUSTOM


def test_allowed_sets_match_matrix() -> None:
    for tier, per_class in _MATRIX.items():
        expected = {cls for cls, ok in per_class.items() if ok}
        assert ALLOWED[tier] == frozenset(expected)
