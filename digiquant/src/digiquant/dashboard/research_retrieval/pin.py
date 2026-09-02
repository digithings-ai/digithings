"""Preflight research-state pin (#2863 / WP12.3).

Select one exact :class:`ResearchStatePin` per run/attempt and carry it for the
whole research/portfolio invocation (including resume). Uses
:class:`ResearchStateStore` selection/pin APIs only — never ``load_latest`` and
never redefines WP12.1 identity helpers.
"""

from __future__ import annotations

from datetime import datetime
from typing import Literal
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field

from digiquant.dashboard.research_retrieval.models import ResearchStatePin, ResearchStateVersion
from digiquant.dashboard.research_retrieval.store import (
    ResearchStateError,
    ResearchStateMissingError,
    ResearchStateStore,
)
from digiquant.dashboard.temporal import require_utc_datetime

STATE_UNAVAILABLE: Literal["state_unavailable"] = "state_unavailable"


class ResearchStateUnavailableError(LookupError):
    """Typed when no usable exact research state can be pinned for a run."""

    reason: Literal["state_unavailable"] = STATE_UNAVAILABLE

    def __init__(self, message: str) -> None:
        super().__init__(message)
        self.reason = STATE_UNAVAILABLE


class ResearchStatePinResult(BaseModel):
    """Outcome of one preflight pin attempt (exact pin or typed unavailable)."""

    model_config = ConfigDict(extra="forbid", frozen=True)

    pin: ResearchStatePin | None = None
    status: Literal["pinned", "state_unavailable"]
    unavailable_reason: str | None = Field(
        default=None,
        description=(
            "Human-readable detail when status is state_unavailable. "
            "Compatibility document path remains shadow-only until exact coverage."
        ),
    )


def _default_requested_as_of(*, knowledge_cutoff_at: datetime) -> datetime:
    """Cutoff-bound as-of: never invent wall-clock beyond the pinned cutoff."""
    return knowledge_cutoff_at


def pin_research_state_for_preflight(
    *,
    store: ResearchStateStore,
    run_id: str,
    attempt_id: str,
    knowledge_cutoff_at: datetime,
    requested_as_of: datetime | None = None,
    explicit_state_version_id: UUID | None = None,
    pinned_at: datetime | None = None,
) -> ResearchStatePinResult:
    """Select once and append an exact run/attempt pin.

    Resume / retry: if ``(run_id, attempt_id)`` already has a pin, reuse it
    (no re-selection as ingestion continues).

    Explicit version: load that exact id (fail → typed ``state_unavailable``).
    Otherwise: one cutoff-bound ``select_state_as_of`` then ``pin_state_for_run``.

    Never calls a latest/current-time fallback.
    """
    run = run_id.strip()
    attempt = attempt_id.strip()
    if not run or not attempt:
        raise ValueError("run_id and attempt_id must be non-empty")

    cutoff = require_utc_datetime(knowledge_cutoff_at, field_name="knowledge_cutoff_at")
    as_of = require_utc_datetime(
        requested_as_of
        if requested_as_of is not None
        else _default_requested_as_of(knowledge_cutoff_at=cutoff),
        field_name="requested_as_of",
    )
    stamp = require_utc_datetime(
        pinned_at if pinned_at is not None else cutoff,
        field_name="pinned_at",
    )
    if stamp < cutoff:
        stamp = cutoff

    existing = store.get_pin(run_id=run, attempt_id=attempt)
    if existing is not None:
        return ResearchStatePinResult(pin=existing, status="pinned")

    version_id: UUID
    if explicit_state_version_id is not None:
        try:
            loaded = store.load_state_version(
                explicit_state_version_id,
                strict=True,
                knowledge_cutoff_at=cutoff,
            )
        except ResearchStateMissingError as exc:
            return ResearchStatePinResult(
                pin=None,
                status=STATE_UNAVAILABLE,
                unavailable_reason=str(exc),
            )
        version_id = loaded.version.state_version_id
        if loaded.version.known_at > cutoff:
            return ResearchStatePinResult(
                pin=None,
                status=STATE_UNAVAILABLE,
                unavailable_reason=(
                    f"explicit state_version_id {version_id} known_at after knowledge_cutoff_at"
                ),
            )
    else:
        selected = store.select_state_as_of(
            requested_as_of=as_of,
            knowledge_cutoff_at=cutoff,
        )
        if selected is None:
            return ResearchStatePinResult(
                pin=None,
                status=STATE_UNAVAILABLE,
                unavailable_reason=(
                    "no strict research state version eligible for "
                    f"requested_as_of={as_of.isoformat()} "
                    f"knowledge_cutoff_at={cutoff.isoformat()}"
                ),
            )
        version_id = selected.state_version_id

    try:
        pin = store.pin_state_for_run(
            ResearchStatePin(
                run_id=run,
                attempt_id=attempt,
                state_version_id=version_id,
                knowledge_cutoff_at=cutoff,
                requested_as_of=as_of,
                pinned_at=stamp,
            )
        )
    except (ResearchStateError, ResearchStateMissingError, ValueError) as exc:
        return ResearchStatePinResult(
            pin=None,
            status=STATE_UNAVAILABLE,
            unavailable_reason=str(exc),
        )
    return ResearchStatePinResult(pin=pin, status="pinned")


def require_research_state_pin(result: ResearchStatePinResult) -> ResearchStatePin:
    """Fail closed for strict readers; shadow callers keep the typed result."""
    if result.status != "pinned" or result.pin is None:
        raise ResearchStateUnavailableError(
            result.unavailable_reason or "research state unavailable for this run"
        )
    return result.pin


def child_version_must_name_parent(
    *,
    pinned: ResearchStatePin,
    child: ResearchStateVersion,
) -> None:
    """Same-run child state versions must name the pinned root as parent."""
    if child.parent_state_version_id != pinned.state_version_id:
        raise ResearchStateError(
            "same-run child ResearchStateVersion must set parent_state_version_id "
            f"to pinned state_version_id {pinned.state_version_id}; "
            f"got {child.parent_state_version_id}"
        )


__all__ = [
    "STATE_UNAVAILABLE",
    "ResearchStatePinResult",
    "ResearchStateUnavailableError",
    "child_version_must_name_parent",
    "pin_research_state_for_preflight",
    "require_research_state_pin",
]
