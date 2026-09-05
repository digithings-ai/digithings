"""Unit tests for portfolio stage gates (#3618).

Covers day-of-week × stage enable/disable combinations, outcome records
(``ran`` / ``disabled`` / ``deferred`` / ``failed``), and the thin calendar hook.
"""

from __future__ import annotations

from datetime import date, datetime, timezone
from types import SimpleNamespace

import pytest
from digiquant.portfolio.stage_gates import (
    BREAKDOWN_KEY,
    MarketCalendarContext,
    PipelineStageReport,
    evaluate_execution_outcome,
    flags_for_run_date,
    outcome_map,
    pipeline_stages_breakdown,
    plan_stage_gates,
    resolve_pipeline_schedule,
    weekday_name,
    with_stage_outcome,
)
from digiquant.profiles import DayStageFlags, PipelineSchedule
from pydantic import ValidationError

pytestmark = pytest.mark.unit


def _schedule(
    *,
    research: bool = True,
    deliberation: bool = True,
    execution: bool = True,
    only: str | None = None,
) -> PipelineSchedule:
    """Build a schedule with uniform flags, or override a single weekday name."""
    day = DayStageFlags(research=research, deliberation=deliberation, execution=execution)
    base = PipelineSchedule.daily_defaults()
    if only is None:
        return PipelineSchedule(
            monday=day,
            tuesday=day,
            wednesday=day,
            thursday=day,
            friday=day,
            saturday=day,
            sunday=day,
        )
    return base.model_copy(update={only: day})


class TestWeekdayAndFlags:
    def test_weekday_name_monday_through_sunday(self) -> None:
        # 2026-09-07 is a Monday.
        assert weekday_name(date(2026, 9, 7)) == "monday"
        assert weekday_name(date(2026, 9, 8)) == "tuesday"
        assert weekday_name(date(2026, 9, 9)) == "wednesday"
        assert weekday_name(date(2026, 9, 10)) == "thursday"
        assert weekday_name(date(2026, 9, 11)) == "friday"
        assert weekday_name(date(2026, 9, 12)) == "saturday"
        assert weekday_name(date(2026, 9, 13)) == "sunday"

    def test_flags_for_run_date_reads_matching_weekday(self) -> None:
        schedule = _schedule(research=False, deliberation=True, execution=False, only="sunday")
        flags = flags_for_run_date(schedule, date(2026, 9, 13))
        assert flags.research is False
        assert flags.deliberation is True
        assert flags.execution is False
        # Other days remain daily defaults.
        mon = flags_for_run_date(schedule, date(2026, 9, 7))
        assert mon.research is True
        assert mon.execution is True


class TestResolveSchedule:
    def test_none_profile_uses_daily_defaults(self) -> None:
        schedule, source = resolve_pipeline_schedule(None)
        assert source == "daily_defaults"
        assert schedule == PipelineSchedule.daily_defaults()

    def test_profile_with_schedule(self) -> None:
        custom = _schedule(execution=False)
        schedule, source = resolve_pipeline_schedule(
            {"pipeline_schedule": custom.model_dump(mode="json")}
        )
        assert source == "profile"
        assert schedule.monday.execution is False

    def test_profile_null_schedule_falls_back(self) -> None:
        schedule, source = resolve_pipeline_schedule(
            {"pipeline_schedule": None, "is_house_default": False}
        )
        assert source == "profile_null_defaults"
        assert schedule.friday.research is True

    def test_house_null_schedule_labeled_house_default(self) -> None:
        schedule, source = resolve_pipeline_schedule(
            {"pipeline_schedule": None, "is_house_default": True}
        )
        assert source == "house_default"
        assert schedule == PipelineSchedule.daily_defaults()


class TestPlanStageGatesDayCombinations:
    @pytest.mark.parametrize(
        ("run_date", "research", "deliberation", "execution", "expected"),
        [
            (
                date(2026, 9, 7),  # Mon
                True,
                True,
                True,
                {"research": "ran", "deliberation": "ran", "execution": "ran"},
            ),
            (
                date(2026, 9, 12),  # Sat — disable execution only
                True,
                True,
                False,
                {"research": "ran", "deliberation": "ran", "execution": "disabled"},
            ),
            (
                date(2026, 9, 13),  # Sun — research only
                True,
                False,
                False,
                {"research": "ran", "deliberation": "disabled", "execution": "disabled"},
            ),
            (
                date(2026, 9, 9),  # Wed — deliberation only
                False,
                True,
                False,
                {"research": "disabled", "deliberation": "ran", "execution": "disabled"},
            ),
            (
                date(2026, 9, 11),  # Fri — all off
                False,
                False,
                False,
                {"research": "disabled", "deliberation": "disabled", "execution": "disabled"},
            ),
        ],
    )
    def test_day_stage_combinations(
        self,
        run_date: date,
        research: bool,
        deliberation: bool,
        execution: bool,
        expected: dict[str, str],
    ) -> None:
        day_name = weekday_name(run_date)
        schedule = _schedule(
            research=research,
            deliberation=deliberation,
            execution=execution,
            only=day_name,
        )
        report = plan_stage_gates(schedule, run_date, schedule_source="profile")
        assert outcome_map(report) == expected
        assert report.weekday == day_name
        assert report.schedule_source == "profile"
        for stage, status in expected.items():
            outcome = report.outcome_for(stage)  # type: ignore[arg-type]
            assert outcome.status == status
            if status == "disabled":
                assert outcome.reason == "schedule_disabled"


class TestExecutionCalendarHook:
    def test_schedule_only_when_calendar_unavailable(self) -> None:
        outcome = evaluate_execution_outcome(
            enabled=True,
            weekday="monday",
            calendar=None,
        )
        assert outcome.status == "ran"
        assert outcome.calendar_checked is False
        assert outcome.reason == "schedule_eligible"

    def test_calendar_none_is_open_does_not_defer(self) -> None:
        outcome = evaluate_execution_outcome(
            enabled=True,
            weekday="tuesday",
            calendar=MarketCalendarContext(is_open=None),
        )
        assert outcome.status == "ran"
        assert outcome.calendar_checked is False

    def test_closed_session_defers(self) -> None:
        next_open = datetime(2026, 9, 8, 13, 30, tzinfo=timezone.utc)
        outcome = evaluate_execution_outcome(
            enabled=True,
            weekday="saturday",
            calendar=MarketCalendarContext(is_open=False, next_eligible_at=next_open),
        )
        assert outcome.status == "deferred"
        assert outcome.reason == "market_session_closed"
        assert outcome.calendar_checked is True
        assert outcome.next_eligible_at == next_open

    def test_open_session_marks_ran(self) -> None:
        outcome = evaluate_execution_outcome(
            enabled=True,
            weekday="friday",
            calendar=MarketCalendarContext(is_open=True, venue="NYSE"),
        )
        assert outcome.status == "ran"
        assert outcome.reason == "session_open"
        assert outcome.calendar_checked is True

    def test_disabled_beats_calendar(self) -> None:
        outcome = evaluate_execution_outcome(
            enabled=False,
            weekday="friday",
            calendar=MarketCalendarContext(is_open=True),
        )
        assert outcome.status == "disabled"
        assert outcome.reason == "schedule_disabled"


class TestOutcomeRecords:
    def test_with_stage_outcome_marks_failed(self) -> None:
        report = plan_stage_gates(PipelineSchedule.daily_defaults(), date(2026, 9, 7))
        updated = with_stage_outcome(
            report,
            "research",
            status="failed",
            reason="research_graph_error",
        )
        assert updated.research.status == "failed"
        assert updated.research.reason == "research_graph_error"
        assert updated.deliberation.status == "ran"
        assert updated.execution.status == "ran"

    def test_report_round_trips_json(self) -> None:
        report = plan_stage_gates(
            _schedule(execution=False, only="sunday"),
            date(2026, 9, 13),
            schedule_source="profile",
        )
        restored = PipelineStageReport.model_validate_json(report.model_dump_json())
        assert restored == report

    def test_rejects_unknown_status(self) -> None:
        report = plan_stage_gates(PipelineSchedule.daily_defaults(), date(2026, 9, 7))
        payload = report.model_dump(mode="json")
        payload["research"]["status"] = "skipped"
        with pytest.raises(ValidationError):
            PipelineStageReport.model_validate(payload)

    def test_breakdown_contributor_reads_state_dump(self) -> None:
        report = plan_stage_gates(PipelineSchedule.daily_defaults(), date(2026, 9, 7))
        state = SimpleNamespace(pipeline_stage_outcomes=report.model_dump(mode="json"))
        fragment = pipeline_stages_breakdown(state)
        assert BREAKDOWN_KEY in fragment
        assert fragment[BREAKDOWN_KEY]["research"]["status"] == "ran"
        assert fragment[BREAKDOWN_KEY]["weekday"] == "monday"

    def test_breakdown_empty_without_outcomes(self) -> None:
        assert pipeline_stages_breakdown(SimpleNamespace()) == {}
        assert pipeline_stages_breakdown(SimpleNamespace(pipeline_stage_outcomes=None)) == {}
