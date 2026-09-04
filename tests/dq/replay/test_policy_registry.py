"""WP16.3 — allowlisted policy registry (#2987)."""

from __future__ import annotations

from datetime import UTC, datetime, timedelta

import pytest
from digiquant.dashboard.replay.models import PolicyBundle, PolicyFamily, PolicyVersionRef
from digiquant.dashboard.replay.policy_registry import (
    PolicyRegistry,
    PolicyRegistryError,
    PolicyRegistryMissingError,
    PolicyRegistryUnavailableError,
    RegisteredPolicyVersion,
)
from digiquant.portfolio.allocation_hashes import sha256_hex

pytestmark = pytest.mark.unit

_CUTOFF = datetime(2024, 6, 15, 12, 0, tzinfo=UTC)
_EARLIER = _CUTOFF - timedelta(days=1)
_LATER = _CUTOFF + timedelta(hours=1)


def _ref(version: RegisteredPolicyVersion) -> PolicyVersionRef:
    return PolicyVersionRef(
        family=version.family,
        version_id=version.version_id,
        content_hash=version.content_hash,
    )


def _registered(
    family: PolicyFamily,
    version_id: str,
    *,
    known_at: datetime = _EARLIER,
    payload: dict[str, object] | None = None,
    review_required: bool = False,
) -> RegisteredPolicyVersion:
    body = payload or {"mode": family.value, "version_id": version_id}
    digest = sha256_hex(body)
    return RegisteredPolicyVersion(
        family=family,
        version_id=version_id,
        content_hash=digest,
        known_at=known_at,
        payload=body,
        review_required=review_required,
    )


def test_resolve_registered_policy_at_cutoff() -> None:
    registry = PolicyRegistry()
    registered = _registered(PolicyFamily.RESEARCH_PLAN, "plan-v1")
    registry.register(registered)

    resolved = registry.resolve(_ref(registered), replay_as_of=_CUTOFF)
    assert resolved.version_id == "plan-v1"
    assert resolved.payload["mode"] == "research_plan"


def test_resolve_rejects_unregistered_version() -> None:
    registry = PolicyRegistry()
    ghost = _registered(PolicyFamily.PORTFOLIO_TARGET, "missing-v1")

    with pytest.raises(PolicyRegistryMissingError, match="missing-v1"):
        registry.resolve(_ref(ghost), replay_as_of=_CUTOFF)


def test_resolve_rejects_future_known_at() -> None:
    registry = PolicyRegistry()
    registered = _registered(PolicyFamily.OBSERVED_SHADOW, "shadow-v1", known_at=_LATER)
    registry.register(registered)

    with pytest.raises(PolicyRegistryError, match="future"):
        registry.resolve(_ref(registered), replay_as_of=_CUTOFF)


def test_resolve_rejects_content_hash_mismatch() -> None:
    registry = PolicyRegistry()
    registered = _registered(PolicyFamily.RESEARCH_PLAN, "plan-v1")
    registry.register(registered)
    ref = PolicyVersionRef(
        family=PolicyFamily.RESEARCH_PLAN,
        version_id="plan-v1",
        content_hash="b" * 64,
    )

    with pytest.raises(PolicyRegistryError, match="content_hash"):
        registry.resolve(ref, replay_as_of=_CUTOFF)


def test_missing_research_output_surfaces_unavailable() -> None:
    registry = PolicyRegistry()
    registered = _registered(
        PolicyFamily.RESEARCH_PLAN,
        "plan-empty",
        payload={"status": "unavailable", "reason": "no_h5_output"},
    )
    registry.register(registered)

    with pytest.raises(PolicyRegistryUnavailableError, match="no_h5_output"):
        registry.resolve(_ref(registered), replay_as_of=_CUTOFF)


def test_review_required_version_must_be_pinned_exactly() -> None:
    registry = PolicyRegistry()
    registered = _registered(
        PolicyFamily.PORTFOLIO_TARGET,
        "target-v2",
        review_required=True,
    )
    registry.register(registered)

    with pytest.raises(PolicyRegistryError, match="explicitly pinned"):
        registry.resolve(_ref(registered), replay_as_of=_CUTOFF)

    resolved = registry.resolve(
        _ref(registered),
        replay_as_of=_CUTOFF,
        review_pinned=True,
    )
    assert resolved.version_id == "target-v2"


def test_resolve_bundle_returns_only_declared_modes() -> None:
    registry = PolicyRegistry()
    plan = _registered(PolicyFamily.RESEARCH_PLAN, "plan-v1")
    target = _registered(PolicyFamily.PORTFOLIO_TARGET, "target-v1")
    registry.register(plan)
    registry.register(target)
    bundle = PolicyBundle(
        research_plan=_ref(plan),
        portfolio_target=_ref(target),
    )

    resolved = registry.resolve_bundle(bundle, replay_as_of=_CUTOFF)
    assert set(resolved) == {"research_plan", "portfolio_target"}


def test_register_conflict_on_same_id_different_hash() -> None:
    registry = PolicyRegistry()
    registry.register(_registered(PolicyFamily.RESEARCH_PLAN, "plan-v1"))

    other = RegisteredPolicyVersion(
        family=PolicyFamily.RESEARCH_PLAN,
        version_id="plan-v1",
        content_hash="c" * 64,
        known_at=_EARLIER,
        payload={"different": True},
    )
    with pytest.raises(PolicyRegistryError, match="conflict"):
        registry.register(other)
