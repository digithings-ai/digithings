"""Overlay run request/result models (shared by runner + execute)."""

from __future__ import annotations

from datetime import date
from decimal import Decimal
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field

from digiquant.olympus.overlay.dispatch import JobStatus, OverlaySkipReason


class OverlayRunRequest(BaseModel):
    """Inputs for one overlay daily run (already entitlement-gated)."""

    model_config = ConfigDict(extra="forbid", frozen=True)

    workspace_id: UUID
    run_date: date
    profile_version_id: UUID
    user_id: UUID | None = None
    research_budget_usd: Decimal | None = Field(default=None, ge=0)
    themes: tuple[str, ...] = ()
    watchlist: tuple[str, ...] = ()


class OverlayRunResult(BaseModel):
    """Visible job outcome — never a silent skip."""

    model_config = ConfigDict(extra="forbid", frozen=True)

    workspace_id: UUID
    status: JobStatus
    skip_reason: OverlaySkipReason | None = None
    spent_usd: Decimal = Decimal("0")
    published_keys: tuple[str, ...] = ()
    carried_keys: tuple[str, ...] = ()
    house_workspace_untouched: bool = True


class PinSeamConfig(BaseModel):
    """Values threaded through preflight — wire, do not redesign the pin loader."""

    model_config = ConfigDict(extra="forbid", frozen=True)

    profile_config_version_id: str | None = None
    workspace_id: str | None = None


class OverlayError(Exception):
    """Structured overlay refusal (``code`` + ``message``)."""

    def __init__(self, code: str, message: str) -> None:
        self.code = code
        self.message = message
        super().__init__(message)


__all__ = [
    "OverlayError",
    "OverlayRunRequest",
    "OverlayRunResult",
    "PinSeamConfig",
]
