"""Unit tests for digiquant.olympus.tenancy (T0, Kairos + tenancy program)."""

from __future__ import annotations

from datetime import datetime, timezone
from uuid import UUID

import pytest
from pydantic import ValidationError

from digiquant.olympus.tenancy import (
    HOUSE_WORKSPACE_SLUG,
    SYSTEM_WORKSPACE_SLUG,
    PlanTier,
    SubscriptionStatus,
    Workspace,
    WorkspaceMember,
    WorkspaceMemberRole,
    WorkspaceType,
    house_workspace_id,
    house_workspace_row,
    system_workspace_id,
    system_workspace_row,
    workspace_id_for_slug,
)

pytestmark = pytest.mark.unit

# Locked deterministic ids — must match migrations 096–098 seed literals.
_SYSTEM_ID = UUID("1105372f-4109-5815-be5a-21091ccfc8ad")
_HOUSE_ID = UUID("6b753576-ced9-5319-9bfa-c5d0aacd9319")


def test_system_and_house_ids_are_stable() -> None:
    assert system_workspace_id() == _SYSTEM_ID
    assert house_workspace_id() == _HOUSE_ID
    assert system_workspace_id() != house_workspace_id()
    assert workspace_id_for_slug(SYSTEM_WORKSPACE_SLUG) == _SYSTEM_ID
    assert workspace_id_for_slug(HOUSE_WORKSPACE_SLUG) == _HOUSE_ID


def test_plan_tier_vocabulary_matches_spec_d1() -> None:
    assert {t.value for t in PlanTier} == {"free", "baseline", "custom", "enterprise"}
    assert "pro" not in {t.value for t in PlanTier}


def test_workspace_types_and_subscription_status() -> None:
    assert {t.value for t in WorkspaceType} == {"system", "user"}
    assert {s.value for s in SubscriptionStatus} == {
        "none",
        "active",
        "past_due",
        "canceled",
    }


def test_seed_row_helpers_mirror_migration_literals() -> None:
    system = system_workspace_row()
    house = house_workspace_row()
    assert system["id"] == str(_SYSTEM_ID)
    assert system["slug"] == "system"
    assert system["type"] == "system"
    assert system["plan_tier"] == "enterprise"
    assert house["id"] == str(_HOUSE_ID)
    assert house["slug"] == "house"
    assert house["type"] == "user"
    assert house["plan_tier"] == "enterprise"
    assert house["subscription_status"] == "active"


def test_workspace_model_accepts_system_seed() -> None:
    now = datetime.now(tz=timezone.utc)
    ws = Workspace(
        id=system_workspace_id(),
        slug=SYSTEM_WORKSPACE_SLUG,
        type=WorkspaceType.SYSTEM,
        name="digithings system",
        created_at=now,
        plan_tier=PlanTier.ENTERPRISE,
        subscription_status=SubscriptionStatus.NONE,
    )
    assert ws.id == _SYSTEM_ID
    assert ws.type is WorkspaceType.SYSTEM


def test_workspace_model_rejects_non_deterministic_system_id() -> None:
    now = datetime.now(tz=timezone.utc)
    with pytest.raises(ValidationError, match="system_workspace_id"):
        Workspace(
            id=UUID("00000000-0000-0000-0000-000000000001"),
            slug=SYSTEM_WORKSPACE_SLUG,
            type=WorkspaceType.SYSTEM,
            name="bogus",
            created_at=now,
        )


def test_workspace_member_model() -> None:
    member = WorkspaceMember(
        workspace_id=house_workspace_id(),
        user_id=UUID("aaaaaaaa-bbbb-cccc-dddd-eeeeeeeeeeee"),
        role=WorkspaceMemberRole.OWNER,
    )
    assert member.role is WorkspaceMemberRole.OWNER
    assert member.workspace_id == _HOUSE_ID
