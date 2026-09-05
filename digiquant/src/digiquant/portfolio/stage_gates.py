"""Per-workspace daily stage gates for the one research→portfolio graph (#3618).

Resolves today's :class:`~digiquant.profiles.pipeline_schedule.PipelineSchedule`
and records typed stage outcomes (``ran`` / ``disabled`` / ``deferred`` /
``failed``). Gates live inside the existing chain — no competing workflows.

Market-hours calendar deferral is a typed thin hook: when no calendar context
is supplied, execution is gated on schedule alone (not deferred).
"""

from __future__ import annotations

from datetime import date, datetime
from typing import Any, Literal, Mapping, Self

from pydantic import BaseModel, ConfigDict

from digiquant.profiles.pipeline_schedule import (
    WEEKDAYS,
    DayStageFlags,
    PipelineSchedule,
    WeekdayName,
)

StageName = Literal["research", "deliberation", "execution"]
StageOutcomeStatus = Literal["ran", "disabled", "deferred", "failed"]
ScheduleSource = Literal[
    "profile",
    "profile_null_defaults",
    "house_default",
    "daily_defaults",
]

BREAKDOWN_KEY = "pipeline_stages"

__all__ = [
    "BREAKDOWN_KEY",
    "CalendarDeferralDecision",
    "MarketCalendarContext",
    "PipelineStageReport",
    "ScheduleSource",
    "StageName",
    "StageOutcome",
    "StageOutcomeStatus",
    "evaluate_execution_outcome",
    "flags_for_run_date",
    "outcome_map",
    "pipeline_stages_breakdown",
    "plan_stage_gates",
    "resolve_pipeline_schedule",
    "weekday_name",
    "with_stage_outcome",
]


class MarketCalendarContext(BaseModel):
    """Typed market-session context for execution deferral (thin until calendar I/O lands).

    ``is_open``:
      - ``True`` / ``False`` — authoritative session state from the venue calendar
      - ``None`` — calendar unavailable; schedule-only gating (do not defer)
    """

    model_config = ConfigDict(extra="forbid", frozen=True)

    is_open: bool | None = None
    venue: str | None = None
    session_start: datetime | None = None
    session_end: datetime | None = None
    next_eligible_at: datetime | None = None
    evaluation_time: datetime | None = None


class CalendarDeferralDecision(BaseModel):
    """Result of the thin calendar deferral hook."""

    model_config = ConfigDict(extra="forbid", frozen=True)

    deferred: bool = False
    reason: str | None = None
    next_eligible_at: datetime | None = None
    calendar_checked: bool = False


class StageOutcome(BaseModel):
    """Typed outcome for one pipeline stage on one run date."""

    model_config = ConfigDict(extra="forbid", frozen=True)

    stage: StageName
    status: StageOutcomeStatus
    weekday: WeekdayName
    reason: str | None = None
    calendar_checked: bool = False
    next_eligible_at: datetime | None = None


class PipelineStageReport(BaseModel):
    """Per-run stage gate report persisted on state / diagnostics breakdown."""

    model_config = ConfigDict(extra="forbid", frozen=True)

    run_date: date
    weekday: WeekdayName
    schedule_source: ScheduleSource
    research: StageOutcome
    deliberation: StageOutcome
    execution: StageOutcome

    def outcome_for(self, stage: StageName) -> StageOutcome:
        return getattr(self, stage)

    @classmethod
    def from_flags(
        cls,
        *,
        run_date: date,
        flags: DayStageFlags,
        schedule_source: ScheduleSource,
        calendar: MarketCalendarContext | None = None,
    ) -> Self:
        """Build an initial report from today's flags (pre-invoke planned statuses)."""
        weekday = weekday_name(run_date)
        research = StageOutcome(
            stage="research",
            status="ran" if flags.research else "disabled",
            weekday=weekday,
            reason=None if flags.research else "schedule_disabled",
        )
        deliberation = StageOutcome(
            stage="deliberation",
            status="ran" if flags.deliberation else "disabled",
            weekday=weekday,
            reason=None if flags.deliberation else "schedule_disabled",
        )
        execution = evaluate_execution_outcome(
            enabled=flags.execution,
            weekday=weekday,
            calendar=calendar,
        )
        return cls(
            run_date=run_date,
            weekday=weekday,
            schedule_source=schedule_source,
            research=research,
            deliberation=deliberation,
            execution=execution,
        )


def weekday_name(run_date: date) -> WeekdayName:
    """Map a :class:`~datetime.date` to a :data:`WEEKDAYS` name (Monday=0)."""
    return WEEKDAYS[run_date.weekday()]


def flags_for_run_date(schedule: PipelineSchedule, run_date: date) -> DayStageFlags:
    """Return today's stage flags from ``schedule``."""
    return schedule.stages_for(weekday_name(run_date))


def resolve_pipeline_schedule(
    profile_config: Mapping[str, Any] | None,
) -> tuple[PipelineSchedule, ScheduleSource]:
    """Resolve a :class:`PipelineSchedule` from a ProfileConfig dump (or defaults).

    ``None`` / missing schedule → house daily defaults (research + deliberation +
    execution enabled every day). Never invents a second cadence.
    """
    if not profile_config:
        return PipelineSchedule.daily_defaults(), "daily_defaults"
    raw_schedule = profile_config.get("pipeline_schedule")
    if raw_schedule is None:
        # Explicit null on a pinned profile — still fall back to daily defaults.
        if profile_config.get("is_house_default") is True:
            return PipelineSchedule.daily_defaults(), "house_default"
        return PipelineSchedule.daily_defaults(), "profile_null_defaults"
    schedule = (
        raw_schedule
        if isinstance(raw_schedule, PipelineSchedule)
        else PipelineSchedule.model_validate(raw_schedule)
    )
    return schedule, "profile"


def evaluate_calendar_deferral(
    calendar: MarketCalendarContext | None,
) -> CalendarDeferralDecision:
    """Thin calendar hook: defer only when ``is_open is False``."""
    if calendar is None or calendar.is_open is None:
        return CalendarDeferralDecision(deferred=False, calendar_checked=False)
    if calendar.is_open is False:
        return CalendarDeferralDecision(
            deferred=True,
            reason="market_session_closed",
            next_eligible_at=calendar.next_eligible_at,
            calendar_checked=True,
        )
    return CalendarDeferralDecision(deferred=False, calendar_checked=True)


def evaluate_execution_outcome(
    *,
    enabled: bool,
    weekday: WeekdayName,
    calendar: MarketCalendarContext | None = None,
) -> StageOutcome:
    """Schedule + thin calendar gate for the execution stage."""
    if not enabled:
        return StageOutcome(
            stage="execution",
            status="disabled",
            weekday=weekday,
            reason="schedule_disabled",
        )
    decision = evaluate_calendar_deferral(calendar)
    if decision.deferred:
        return StageOutcome(
            stage="execution",
            status="deferred",
            weekday=weekday,
            reason=decision.reason,
            calendar_checked=decision.calendar_checked,
            next_eligible_at=decision.next_eligible_at,
        )
    return StageOutcome(
        stage="execution",
        status="ran",
        weekday=weekday,
        reason="schedule_eligible" if not decision.calendar_checked else "session_open",
        calendar_checked=decision.calendar_checked,
        next_eligible_at=decision.next_eligible_at,
    )


def plan_stage_gates(
    schedule: PipelineSchedule,
    run_date: date,
    *,
    schedule_source: ScheduleSource = "daily_defaults",
    calendar: MarketCalendarContext | None = None,
) -> PipelineStageReport:
    """Pure planner: today's flags → initial stage outcomes (before invoke)."""
    flags = flags_for_run_date(schedule, run_date)
    return PipelineStageReport.from_flags(
        run_date=run_date,
        flags=flags,
        schedule_source=schedule_source,
        calendar=calendar,
    )


def with_stage_outcome(
    report: PipelineStageReport,
    stage: StageName,
    *,
    status: StageOutcomeStatus,
    reason: str | None = None,
) -> PipelineStageReport:
    """Return a copy of ``report`` with one stage outcome replaced."""
    current = report.outcome_for(stage)
    updated = current.model_copy(
        update={
            "status": status,
            "reason": reason if reason is not None else current.reason,
        }
    )
    return report.model_copy(update={stage: updated})


def outcome_map(report: PipelineStageReport) -> dict[str, str]:
    """``{stage: status}`` helper for tests and compact logs."""
    return {
        "research": report.research.status,
        "deliberation": report.deliberation.status,
        "execution": report.execution.status,
    }


def pipeline_stages_breakdown(state: Any) -> dict[str, Any]:
    """Diagnostics breakdown contributor — folds ``pipeline_stage_outcomes`` into jsonb."""
    raw = getattr(state, "pipeline_stage_outcomes", None)
    if not raw:
        return {}
    if isinstance(raw, PipelineStageReport):
        payload = raw.model_dump(mode="json")
    elif isinstance(raw, Mapping):
        payload = dict(raw)
    else:
        return {}
    return {BREAKDOWN_KEY: payload}
