"""Unit tests for ``PipelineSchedule`` and ``ExecutionPolicy`` contracts (#3611).

Covers daily defaults, validation, JSON serialization, and house-key invariants
when nested under ``ProfileConfig``.
"""

from __future__ import annotations

from uuid import NAMESPACE_URL, uuid5

import pytest
from digiquant.dashboard.profile_config import (
    HOUSE_PROFILE_KEY,
    ProfileConfig,
    house_profile_config,
)
from digiquant.profiles import (
    WEEKDAYS,
    DayStageFlags,
    ExecutionPolicy,
    InvestmentProfile,
    PipelineSchedule,
)
from pydantic import ValidationError

pytestmark = pytest.mark.unit


def _moderate_investment() -> InvestmentProfile:
    return InvestmentProfile(
        risk_tolerance="moderate",
        horizon_years=10,
        liquidity_needs="medium",
        base_currency="USD",
        tax_jurisdiction="US",
        esg_preference="none",
        experience_level="intermediate",
    )


class TestPipelineSchedule:
    def test_daily_defaults_enable_all_stages_every_day(self) -> None:
        schedule = PipelineSchedule.daily_defaults()
        assert schedule.schema_version == 1
        assert list(WEEKDAYS) == [
            "monday",
            "tuesday",
            "wednesday",
            "thursday",
            "friday",
            "saturday",
            "sunday",
        ]
        for day in WEEKDAYS:
            flags = schedule.stages_for(day)
            assert flags.research is True
            assert flags.deliberation is True
            assert flags.execution is True

    def test_round_trips_json(self) -> None:
        original = PipelineSchedule.daily_defaults()
        restored = PipelineSchedule.model_validate_json(original.model_dump_json())
        assert restored == original
        assert restored.model_dump() == original.model_dump()

    def test_rejects_extra_day_field(self) -> None:
        payload = PipelineSchedule.daily_defaults().model_dump()
        payload["bluesday"] = {"research": True, "deliberation": True, "execution": True}
        with pytest.raises(ValidationError):
            PipelineSchedule.model_validate(payload)

    def test_rejects_non_bool_stage_flag(self) -> None:
        payload = PipelineSchedule.daily_defaults().model_dump()
        payload["monday"]["research"] = ["not", "a", "bool"]
        with pytest.raises(ValidationError):
            PipelineSchedule.model_validate(payload)

    def test_requires_all_weekdays(self) -> None:
        with pytest.raises(ValidationError):
            PipelineSchedule.model_validate({"schema_version": 1, "monday": DayStageFlags()})

    def test_per_day_override_preserves_others(self) -> None:
        schedule = PipelineSchedule.daily_defaults().model_copy(
            update={"sunday": DayStageFlags(research=True, deliberation=False, execution=False)}
        )
        assert schedule.sunday.deliberation is False
        assert schedule.sunday.execution is False
        assert schedule.monday.execution is True


class TestExecutionPolicy:
    def test_defaults_are_calendar_vetoable(self) -> None:
        policy = ExecutionPolicy.defaults()
        assert policy.schema_version == 1
        assert policy.calendar_mode == "venue_calendar"
        assert policy.on_closed_session == "defer"
        assert policy.respect_early_close is True
        assert policy.permitted_venues == []

    def test_round_trips_json(self) -> None:
        original = ExecutionPolicy(
            permitted_venues=["nyse", "NASDAQ", "nyse"],
            respect_early_close=False,
        )
        restored = ExecutionPolicy.model_validate_json(original.model_dump_json())
        assert restored.permitted_venues == ["NYSE", "NASDAQ"]
        assert restored.respect_early_close is False
        assert restored.calendar_mode == "venue_calendar"

    def test_rejects_unknown_calendar_mode(self) -> None:
        with pytest.raises(ValidationError):
            ExecutionPolicy.model_validate({"calendar_mode": "always_open"})

    def test_rejects_force_open_closed_session_behavior(self) -> None:
        with pytest.raises(ValidationError):
            ExecutionPolicy.model_validate({"on_closed_session": "force"})

    def test_rejects_extra_fields(self) -> None:
        with pytest.raises(ValidationError):
            ExecutionPolicy.model_validate({"bypass_calendar": True})


class TestProfileConfigScheduleFields:
    def test_house_profile_includes_schedule_defaults(self) -> None:
        cfg = house_profile_config()
        assert cfg.is_house_default is True
        assert cfg.profile_key == HOUSE_PROFILE_KEY
        assert cfg.pipeline_schedule == PipelineSchedule.daily_defaults()
        assert cfg.execution_policy == ExecutionPolicy.defaults()

    def test_overlay_accepts_optional_schedule_fields(self) -> None:
        cfg = ProfileConfig(
            version_id=uuid5(NAMESPACE_URL, "user:sched:v1"),
            profile_key="user:sched",
            is_house_default=False,
            label="Scheduled overlay",
            investment=_moderate_investment(),
            pipeline_schedule=PipelineSchedule.daily_defaults(),
            execution_policy=ExecutionPolicy(permitted_venues=["PAPER_INTERNAL"]),
        )
        assert cfg.pipeline_schedule is not None
        assert cfg.execution_policy is not None
        assert cfg.execution_policy.permitted_venues == ["PAPER_INTERNAL"]

    def test_overlay_cannot_claim_house_key_with_schedule(self) -> None:
        with pytest.raises(ValidationError):
            ProfileConfig(
                version_id=uuid5(NAMESPACE_URL, "overlay-bad-sched"),
                profile_key=HOUSE_PROFILE_KEY,
                is_house_default=False,
                label="bad",
                pipeline_schedule=PipelineSchedule.daily_defaults(),
                execution_policy=ExecutionPolicy.defaults(),
            )

    def test_schedule_fields_round_trip_in_profile_payload(self) -> None:
        cfg = ProfileConfig(
            version_id=uuid5(NAMESPACE_URL, "user:roundtrip"),
            profile_key="workspace",
            is_house_default=False,
            label="Round trip",
            pipeline_schedule=PipelineSchedule.daily_defaults().model_copy(
                update={
                    "saturday": DayStageFlags(research=False, deliberation=False, execution=False)
                }
            ),
            execution_policy=ExecutionPolicy.defaults(),
        )
        restored = ProfileConfig.model_validate(cfg.model_dump(mode="json"))
        assert restored.pipeline_schedule is not None
        assert restored.pipeline_schedule.saturday.research is False
        assert restored.execution_policy == ExecutionPolicy.defaults()
