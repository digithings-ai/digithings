"""Versioned Pydantic v2 schema for workspace pipeline stage scheduling.

``PipelineSchedule`` is a seven-weekday × three-stage boolean matrix consumed by
the daily research/portfolio graph (later) and the settings Pipeline tab (later).
It records *user scheduling intent* only — market-calendar veto lives on
:class:`~digiquant.profiles.execution_policy.ExecutionPolicy` and is never
overridden by a scheduled ``execution=True`` day.

See ``digiquant/docs/profiles/README.md``.
"""

from __future__ import annotations

from typing import Literal, Self

from pydantic import BaseModel, ConfigDict, Field

WEEKDAYS: tuple[
    Literal[
        "monday",
        "tuesday",
        "wednesday",
        "thursday",
        "friday",
        "saturday",
        "sunday",
    ],
    ...,
] = (
    "monday",
    "tuesday",
    "wednesday",
    "thursday",
    "friday",
    "saturday",
    "sunday",
)

WeekdayName = Literal[
    "monday",
    "tuesday",
    "wednesday",
    "thursday",
    "friday",
    "saturday",
    "sunday",
]


class DayStageFlags(BaseModel):
    """Per-day enablement for research, deliberation, and execution stages."""

    model_config = ConfigDict(extra="forbid", frozen=True)

    research: bool = Field(
        default=True,
        description="Run research (evidence / source refresh) on this weekday.",
    )
    deliberation: bool = Field(
        default=True,
        description="Run portfolio deliberation (H1–H9 intent) on this weekday.",
    )
    execution: bool = Field(
        default=True,
        description=(
            "Schedule execution on this weekday. Still subject to the "
            "authoritative market-calendar veto — never forces a closed session."
        ),
    )


class PipelineSchedule(BaseModel):
    """Seven-day × three-stage schedule for the one daily graph (schema v1).

    Defaults enable research, deliberation, and execution every day. Execution
    days remain calendar-vetoable via :class:`ExecutionPolicy` — a scheduled
    execution on a closed market defers; it never overrides the calendar.
    """

    model_config = ConfigDict(extra="forbid", frozen=True)

    schema_version: int = Field(
        default=1,
        ge=1,
        description="Schema version; bump on breaking changes.",
    )
    monday: DayStageFlags
    tuesday: DayStageFlags
    wednesday: DayStageFlags
    thursday: DayStageFlags
    friday: DayStageFlags
    saturday: DayStageFlags
    sunday: DayStageFlags

    @classmethod
    def daily_defaults(cls) -> Self:
        """Research + deliberation + execution enabled on every weekday."""
        day = DayStageFlags()
        return cls(
            monday=day,
            tuesday=day,
            wednesday=day,
            thursday=day,
            friday=day,
            saturday=day,
            sunday=day,
        )

    def stages_for(self, weekday: WeekdayName) -> DayStageFlags:
        """Return the stage flags for one weekday name."""
        return getattr(self, weekday)
