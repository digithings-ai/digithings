"""Workspace tenancy contracts (T0, Kairos + tenancy program, #5-T0).

Multi-tenant privacy boundary: every private row (positions, fills, ledger, accounting,
overlay profile config, …) is scoped to a ``workspace_id``. Exactly one workspace has
``type='system'`` — the shared, tenant-agnostic research corpus lives there — and the
digithings operator's own current book lives under the **house** workspace, a regular
``type='user'`` row seeded alongside it so existing single-tenant data has somewhere to
backfill to.

This module is deliberately schema-adjacent, not schema-owning: the DDL lives in
``digiquant/supabase/migrations/096_workspaces_tenancy_tables.sql`` and friends. What
lives here is the typed contract the schema is expected to satisfy, and the
deterministic ids that let the migration's seed rows and every Python writer agree on
"the system workspace" / "the house workspace" without a round trip.

Scope note (binding behavior #4 in the T0 briefing): RLS policy CHECKs against
``plan_tier`` tiers land in T5's policy pass, not here. This module only defines the
closed vocabulary the CHECK constraint and the JWT claim both draw from.
"""

from __future__ import annotations

from datetime import datetime
from enum import StrEnum
from typing import Any  # score:allow untyped any — jsonb config columns round-trip as dict
from uuid import NAMESPACE_URL, UUID, uuid5

from pydantic import BaseModel, ConfigDict, Field, model_validator

# Fixed namespace for every deterministic id this module mints. Mirrors
# ``profile_config._PROFILE_VERSION_NS`` / migration 075's house seed comment — any
# stable literal works here, it only needs to never change between deploys.
_TENANCY_NAMESPACE = uuid5(NAMESPACE_URL, "digithings.olympus.tenancy")

SYSTEM_WORKSPACE_SLUG = "system"
HOUSE_WORKSPACE_SLUG = "house"


class WorkspaceType(StrEnum):
    """Closed vocabulary for ``workspaces.type`` — exactly one ``SYSTEM`` row exists."""

    SYSTEM = "system"
    USER = "user"


class PlanTier(StrEnum):
    """Billing tier vocabulary (spec D1; supersedes the roadmap's ``free|pro|enterprise``
    sketch — ``baseline``/``custom`` replace ``pro`` per the locked spec decision)."""

    FREE = "free"
    BASELINE = "baseline"
    CUSTOM = "custom"
    ENTERPRISE = "enterprise"


class SubscriptionStatus(StrEnum):
    """Closed vocabulary for ``workspaces.subscription_status`` (roadmap P2a/A.5)."""

    NONE = "none"
    ACTIVE = "active"
    PAST_DUE = "past_due"
    CANCELED = "canceled"


class WorkspaceMemberRole(StrEnum):
    """Closed vocabulary for ``workspace_members.role``."""

    OWNER = "owner"
    MEMBER = "member"


def workspace_id_for_slug(slug: str) -> UUID:
    """Deterministic workspace id for a well-known slug (``system``, ``house``, …).

    Not for arbitrary user workspaces — those get ``gen_random_uuid()`` at signup. This
    is only for the handful of slugs a migration seed and Python code must agree on
    without a database round trip.
    """
    return uuid5(_TENANCY_NAMESPACE, f"workspace:{slug}")


def system_workspace_id() -> UUID:
    """The one ``type='system'`` workspace — shared, tenant-agnostic research corpus."""
    return workspace_id_for_slug(SYSTEM_WORKSPACE_SLUG)


def house_workspace_id() -> UUID:
    """The digithings operator's own workspace — where pre-T0 single-tenant data backfills.

    Every Python writer in the private set (``ledger_io``, ``execution_io``,
    ``opening_snapshot``, ``accounting.io``, ``commit_io``, ``execute_at_open``) stamps
    this id on rows it does not otherwise have a workspace for. It is a regular
    ``type='user'`` row, not the system workspace — the house *book* is user-private
    data, even though the house *research* (Atlas corpus) is shared under the system
    workspace.
    """
    return workspace_id_for_slug(HOUSE_WORKSPACE_SLUG)


def resolved_workspace_id(raw: UUID | str | None) -> UUID:
    """Omitted / ``None`` / blank means **the house workspace**, never "every row".

    House readers and writers that leave ``workspace_id`` off must still filter
    and stamp ``house_workspace_id()``. Overlay passes an explicit id.
    """
    if raw is None:
        return house_workspace_id()
    text = str(raw).strip()
    if not text:
        return house_workspace_id()
    return UUID(text)


def eq_house_workspace(query: Any, workspace_id: UUID | str | None = None) -> Any:
    """Pin a PostgREST query to one workspace. Omitted id means the house book.

    Overlay same-date Group A rows must not leak into house ops readers. Duck-typed
    for supabase-py and ``FakeSupabaseClient`` (both expose ``.eq``).
    """
    return query.eq("workspace_id", str(resolved_workspace_id(workspace_id)))


class Workspace(BaseModel):
    """One row of ``public.workspaces`` (roadmap P2a; billing columns per spec D1/D8).

    Config columns (``investment_profile``, ``preferences``, ``rebalancing_policy``,
    ``settings``) are typed ``dict[str, Any] | None`` here rather than the richer
    ``InvestmentProfile``/``AssetPreferences`` models ``profile_config.py`` uses — T0
    only needs the column to exist and round-trip; T3/T4 wire real validation when the
    settings UI + BFF PATCH land (roadmap P5).
    """

    model_config = ConfigDict(extra="forbid", frozen=True, str_strip_whitespace=True)

    id: UUID
    slug: str | None = Field(default=None, max_length=100)
    type: WorkspaceType
    name: str | None = None
    created_at: datetime
    stripe_customer_id: str | None = None
    stripe_subscription_id: str | None = None
    subscription_status: SubscriptionStatus = SubscriptionStatus.NONE
    plan_tier: PlanTier = PlanTier.FREE
    investment_profile: dict[str, Any] | None = None
    preferences: dict[str, Any] | None = None
    rebalancing_policy: dict[str, Any] | None = None
    settings: dict[str, Any] | None = None
    published_profile_version: int = Field(default=0, ge=0)
    updated_at: datetime | None = None

    @model_validator(mode="after")
    def _system_workspace_invariants(self) -> Workspace:
        if self.type is WorkspaceType.SYSTEM and self.id != system_workspace_id():
            raise ValueError(
                "a WorkspaceType.SYSTEM row must use the deterministic system_workspace_id()"
            )
        return self


class WorkspaceMember(BaseModel):
    """One row of ``public.workspace_members`` (roadmap P2a)."""

    model_config = ConfigDict(extra="forbid", frozen=True)

    workspace_id: UUID
    user_id: UUID
    role: WorkspaceMemberRole = WorkspaceMemberRole.OWNER


def house_workspace_row() -> dict[str, Any]:
    """The seed row the T0 migration inserts for the house workspace, mirrored here so a
    Python-side test can assert the migration's literal id/slug against this module's
    deterministic helper instead of a second hardcoded UUID literal."""
    return {
        "id": str(house_workspace_id()),
        "slug": HOUSE_WORKSPACE_SLUG,
        "type": WorkspaceType.USER.value,
        "name": "digithings house",
        "plan_tier": PlanTier.ENTERPRISE.value,
        "subscription_status": SubscriptionStatus.ACTIVE.value,
    }


def system_workspace_row() -> dict[str, Any]:
    """The seed row the T0 migration inserts for the system workspace."""
    return {
        "id": str(system_workspace_id()),
        "slug": SYSTEM_WORKSPACE_SLUG,
        "type": WorkspaceType.SYSTEM.value,
        "name": "digithings system",
        "plan_tier": PlanTier.ENTERPRISE.value,
        "subscription_status": SubscriptionStatus.NONE.value,
    }


__all__ = [
    "HOUSE_WORKSPACE_SLUG",
    "PlanTier",
    "SYSTEM_WORKSPACE_SLUG",
    "SubscriptionStatus",
    "Workspace",
    "WorkspaceMember",
    "WorkspaceMemberRole",
    "WorkspaceType",
    "eq_house_workspace",
    "house_workspace_id",
    "house_workspace_row",
    "resolved_workspace_id",
    "system_workspace_id",
    "system_workspace_row",
    "workspace_id_for_slug",
]
