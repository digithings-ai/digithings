"""Overlay private-phase persistence gate (T4).

Migration 110 narrows ``anon_read`` on workspace-scoped private books
(``documents`` / ``positions`` / ``nav_history`` / ``portfolio_metrics``) to the
house (and house+system for documents). Overlay may persist **documents** once
an operator sets ``OLYMPUS_OVERLAY_PERSIST=1`` on a target that has 110
applied. Cutover 900 is still required before dropping the house teaser for
anon / free JWTs; it is not the persist precondition.

``positions`` / ``nav_history`` / ``portfolio_metrics`` / ``position_events``
still carry migration 097's legacy single-tenant arbiters
(``PRIMARY KEY (date)`` / ``UNIQUE(date, ticker)`` / ``UNIQUE(date)``) beside
the widened ``(workspace_id, …)`` keys. House ops writers on ``develop`` now
target those widened keys, but the legacy arbiters still reject a second
workspace's same-date row (and ``main`` house GHA must be on the widened
conflict before the drop can be applied). An overlay row for the same calendar
date therefore still fails the leftover unique. ``require_overlay_legacy_book_safe``
refuses those writes until staged cutover 113
(``migrations/cutover/113_drop_legacy_book_uniques.sql``) is **applied** on
the target — staging the file under ``cutover/`` does not lift this gate.

Ledger ``uq_portfolio_ledger_commits_one_root`` is likewise ``(run_date)`` only
(migration 069) until 113 widens it to ``(workspace_id, run_date)`` —
overlay + house cannot both root a commit on the same date until then.

``daily_snapshots`` stays a house-only ``UNIQUE(date)`` table — overlay
publish must skip it (see ``publish_phase``) even with persist on.
"""

from __future__ import annotations

import os
from uuid import UUID

from digiquant.olympus.overlay.dispatch import JobStatus
from digiquant.olympus.tenancy import house_workspace_id, resolved_workspace_id, system_workspace_id

OVERLAY_PERSIST_ENV = "OLYMPUS_OVERLAY_PERSIST"
OVERLAY_DOC_PREFIX = "overlay/"
LEGACY_BOOK_UNIQUE_CODE = "legacy_book_unique"


class OverlayPersistDisabled(Exception):
    """Private-phase write refused because overlay persist is off."""

    def __init__(self) -> None:
        self.code = JobStatus.PERSIST_DISABLED.value
        self.message = (
            "overlay private-phase persistence is disabled; set "
            f"{OVERLAY_PERSIST_ENV}=1 only after migration 110 "
            "(anon house-only on private books) is applied on the target"
        )
        super().__init__(self.message)


class OverlayLegacyBookBlocked(Exception):
    """Overlay positions/NAV/ledger write refused while legacy UNIQUEs remain."""

    def __init__(self) -> None:
        self.code = LEGACY_BOOK_UNIQUE_CODE
        self.message = (
            "overlay positions/nav_history/ledger writes are blocked while "
            "legacy UNIQUE(date) / UNIQUE(date,ticker) and ledger "
            "one-root-per-run_date still apply; "
            f"{OVERLAY_PERSIST_ENV}=1 after migration 110 only covers documents. "
            "Staged cutover 113 drops those arbiters; do not lift this gate "
            "until 113 is applied on the target after main house GHA writers "
            "use the widened conflict"
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


def require_overlay_legacy_book_safe(workspace_id: UUID | str | None) -> None:
    """Refuse overlay book/ledger writes until legacy single-tenant UNIQUEs are gone.

    Documents remain gated only by :func:`require_overlay_persist`.
    """
    if is_private_workspace(workspace_id):
        raise OverlayLegacyBookBlocked()


def hermes_document_key(base: str, workspace_id: UUID | str | None) -> str:
    """House keys stay unprefixed. Overlay H7/H8 keys are ``overlay/{ws}/{base}``."""
    if not is_private_workspace(workspace_id):
        return base
    return f"{OVERLAY_DOC_PREFIX}{resolved_workspace_id(workspace_id)}/{base}"


__all__ = [
    "LEGACY_BOOK_UNIQUE_CODE",
    "OVERLAY_DOC_PREFIX",
    "OVERLAY_PERSIST_ENV",
    "OverlayLegacyBookBlocked",
    "OverlayPersistDisabled",
    "hermes_document_key",
    "is_private_workspace",
    "overlay_persist_enabled",
    "require_overlay_legacy_book_safe",
    "require_overlay_persist",
]
