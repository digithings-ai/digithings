"""Overlay private-phase persistence gate (T4 / T1-train precondition).

``documents`` / ``positions`` / ``nav_history`` still carry ``anon_read USING (true)``
until the T1-train anon-policy drop. Overlay must not write private rows onto that
surface unless an operator has explicitly enabled persistence after that drop.
"""

from __future__ import annotations

import os
from uuid import UUID

from digiquant.olympus.overlay.dispatch import JobStatus
from digiquant.olympus.tenancy import house_workspace_id, resolved_workspace_id, system_workspace_id

OVERLAY_PERSIST_ENV = "OLYMPUS_OVERLAY_PERSIST"
OVERLAY_DOC_PREFIX = "overlay/"


class OverlayPersistDisabled(Exception):
    """Private-phase write refused because overlay persist is off."""

    def __init__(self) -> None:
        self.code = JobStatus.PERSIST_DISABLED.value
        self.message = (
            "overlay private-phase persistence is disabled; set "
            f"{OVERLAY_PERSIST_ENV}=1 only after the T1-train anon-policy drop"
        )
        super().__init__(self.message)


def overlay_persist_enabled() -> bool:
    return os.environ.get(OVERLAY_PERSIST_ENV, "").strip() == "1"


def is_private_workspace(workspace_id: UUID | str | None) -> bool:
    """True when the id is a tenant workspace (not house, not system, not omitted)."""
    if workspace_id is None or not str(workspace_id).strip():
        return False
    scoped = resolved_workspace_id(workspace_id)
    return scoped not in {house_workspace_id(), system_workspace_id()}


def require_overlay_persist(workspace_id: UUID | str | None) -> None:
    if is_private_workspace(workspace_id) and not overlay_persist_enabled():
        raise OverlayPersistDisabled()


def hermes_document_key(base: str, workspace_id: UUID | str | None) -> str:
    """House keys stay unprefixed. Overlay H7/H8 keys are ``overlay/{ws}/{base}``."""
    if not is_private_workspace(workspace_id):
        return base
    return f"{OVERLAY_DOC_PREFIX}{resolved_workspace_id(workspace_id)}/{base}"


__all__ = [
    "OVERLAY_DOC_PREFIX",
    "OVERLAY_PERSIST_ENV",
    "OverlayPersistDisabled",
    "hermes_document_key",
    "is_private_workspace",
    "overlay_persist_enabled",
    "require_overlay_persist",
]
