"""Versioned Pydantic v2 schema for workspace execution policy.

Companion to :class:`~digiquant.profiles.pipeline_schedule.PipelineSchedule`.
``PipelineSchedule.execution`` records *when* the user wants execution attempted;
``ExecutionPolicy`` records *how* calendar/session and venue preferences constrain
that intent. The venue calendar is authoritative: a scheduled execution day on a
closed market defers — it never overrides the calendar.

Distinct from ``digiquant.dashboard.replay.models.ExecutionPolicy`` (replay fill
assumptions). This module is the workspace settings / ProfileConfig contract.

See ``digiquant/docs/profiles/README.md``.
"""

from __future__ import annotations

from typing import Literal, Self

from pydantic import BaseModel, ConfigDict, Field, field_validator

CalendarMode = Literal["venue_calendar"]
ClosedSessionBehavior = Literal["defer"]


class ExecutionPolicy(BaseModel):
    """Workspace execution constraints (schema v1).

    Attributes
    ----------
    schema_version
        Monotonic schema version. Increment only on breaking changes.
    calendar_mode
        How market availability is resolved. ``venue_calendar`` is the only v1
        mode — the authoritative venue calendar always wins over schedule intent.
    permitted_venues
        Preferred venue identifiers (upper-cased, de-duplicated). Empty means no
        preference filter; the calendar still applies to whatever venue is chosen.
    on_closed_session
        Behavior when the applicable session is closed (or past an early close).
        ``defer`` leaves valid intent pending — never force-opens a closed market.
    respect_early_close
        When true, treat post-early-close windows as closed for new execution.
    """

    model_config = ConfigDict(extra="forbid", frozen=True, str_strip_whitespace=True)

    schema_version: int = Field(
        default=1,
        ge=1,
        description="Schema version; bump on breaking changes.",
    )
    calendar_mode: CalendarMode = Field(
        default="venue_calendar",
        description=(
            "Authoritative venue calendar; scheduled execution cannot override closed sessions."
        ),
    )
    permitted_venues: list[str] = Field(
        default_factory=list,
        description=(
            "Preferred venues (upper-cased, de-duplicated). Empty = no preference "
            "filter; calendar still applies."
        ),
    )
    on_closed_session: ClosedSessionBehavior = Field(
        default="defer",
        description="Closed sessions defer pending intent; never force execution.",
    )
    respect_early_close: bool = Field(
        default=True,
        description="Treat early-close windows as closed for new execution afterward.",
    )

    @field_validator("permitted_venues", mode="after")
    @classmethod
    def _normalize_venues(cls, value: list[str]) -> list[str]:
        """Upper-case, strip, drop empties, and de-duplicate while keeping order."""
        seen: dict[str, None] = {}
        for raw in value:
            if not isinstance(raw, str):
                raise TypeError(f"permitted_venues entries must be str, got {type(raw)!r}")
            normalized = raw.strip().upper()
            if not normalized:
                continue
            seen.setdefault(normalized, None)
        return list(seen)

    @classmethod
    def defaults(cls) -> Self:
        """Calendar-vetoable daily execution policy (venue calendar + defer)."""
        return cls()
