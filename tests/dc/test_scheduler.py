"""Unit tests for digiclaw cron parsing and scheduler (#218 / CHR-63)."""

from __future__ import annotations

from datetime import datetime, timedelta, timezone
from pathlib import Path

import pytest
from digiclaw.cron import CronParseError, next_cron_time, parse_cron
from digiclaw.schedule_schema import (
    AgentDefinition,
    AgentSchedule,
    ScheduleMode,
    ScheduleSchemaError,
    load_agent_definition,
    load_agent_definitions,
)
from digiclaw.scheduler import (
    JsonStateStore,
    LifecycleState,
    Scheduler,
    SchedulerError,
)
from pydantic import ValidationError


@pytest.mark.unit
def test_parse_cron_every_thirty_minutes() -> None:
    cron = parse_cron("*/30 * * * *")
    assert cron.minute == frozenset({0, 30})
    assert 0 in cron.hour and 23 in cron.hour


@pytest.mark.unit
def test_parse_cron_rejects_bad_field_count() -> None:
    with pytest.raises(CronParseError) as exc:
        parse_cron("0 9 * *")
    assert exc.value.code == "cron_invalid"


@pytest.mark.unit
def test_next_cron_time_is_strictly_after() -> None:
    after = datetime(2026, 8, 27, 12, 0, tzinfo=timezone.utc)
    nxt = next_cron_time("*/30 * * * *", after=after)
    assert nxt == datetime(2026, 8, 27, 12, 30, tzinfo=timezone.utc)


@pytest.mark.unit
def test_next_cron_time_weekday_names() -> None:
    # 2026-08-27 is a Thursday; next Monday 09:00 UTC
    after = datetime(2026, 8, 27, 8, 0, tzinfo=timezone.utc)
    nxt = next_cron_time("0 9 * * MON", after=after)
    assert nxt == datetime(2026, 8, 31, 9, 0, tzinfo=timezone.utc)


@pytest.mark.unit
def test_load_agent_definition_from_yaml(tmp_path: Path) -> None:
    path = tmp_path / "nightly.yaml"
    path.write_text(
        "name: nightly\nschedule:\n  mode: cron\n  cron: '0 2 * * *'\n",
        encoding="utf-8",
    )
    agent = load_agent_definition(path)
    assert agent.name == "nightly"
    assert agent.schedule.mode is ScheduleMode.CRON
    assert agent.schedule.cron == "0 2 * * *"


@pytest.mark.unit
def test_continuous_schedule_requires_interval() -> None:
    with pytest.raises(ValidationError):
        AgentSchedule(mode=ScheduleMode.CONTINUOUS)


@pytest.mark.unit
def test_scheduler_continuous_tick_and_isolation(tmp_path: Path) -> None:
    state_path = tmp_path / "state.json"
    calls: list[str] = []

    def runner(agent: AgentDefinition) -> None:
        calls.append(agent.name)
        if agent.name == "flaky":
            raise RuntimeError("boom")

    agents = [
        AgentDefinition(
            name="flaky",
            schedule=AgentSchedule(mode=ScheduleMode.CONTINUOUS, interval_seconds=10),
        ),
        AgentDefinition(
            name="steady",
            schedule=AgentSchedule(mode=ScheduleMode.CONTINUOUS, interval_seconds=10),
        ),
    ]
    sched = Scheduler(
        definitions=agents,
        state_store=JsonStateStore(state_path),
        runner=runner,
    )
    t0 = datetime(2026, 8, 27, 12, 0, tzinfo=timezone.utc)
    sched.start("flaky", now=t0)
    sched.start("steady", now=t0)

    outcomes = sched.tick(now=t0)
    assert {o.name: o.ok for o in outcomes} == {"flaky": False, "steady": True}
    assert calls == ["flaky", "steady"]

    status = {row.name: row for row in sched.status()}
    assert status["flaky"].last_status == "error"
    assert status["flaky"].next_run_at == t0 + timedelta(seconds=10)
    assert status["steady"].last_status == "ok"
    assert status["steady"].next_run_at == t0 + timedelta(seconds=10)

    outcomes2 = sched.tick(now=t0 + timedelta(seconds=10))
    assert len(outcomes2) == 2
    assert calls == ["flaky", "steady", "flaky", "steady"]


@pytest.mark.unit
def test_scheduler_cron_next_run_and_status(tmp_path: Path) -> None:
    agents = [
        AgentDefinition(
            name="cronny",
            schedule=AgentSchedule(mode=ScheduleMode.CRON, cron="0 * * * *"),
        )
    ]
    sched = Scheduler(
        definitions=agents,
        state_store=JsonStateStore(tmp_path / "state.json"),
        runner=lambda _a: None,
    )
    t0 = datetime(2026, 8, 27, 12, 15, tzinfo=timezone.utc)
    sched.start("cronny", now=t0)
    row = sched.status()[0]
    assert row.lifecycle is LifecycleState.RUNNING
    assert row.next_run_at == datetime(2026, 8, 27, 13, 0, tzinfo=timezone.utc)

    assert sched.tick(now=t0) == []
    outcomes = sched.tick(now=datetime(2026, 8, 27, 13, 0, tzinfo=timezone.utc))
    assert len(outcomes) == 1 and outcomes[0].ok


@pytest.mark.unit
def test_scheduler_restart_requeues_pending(tmp_path: Path) -> None:
    state_path = tmp_path / "state.json"
    agents = [
        AgentDefinition(
            name="loop",
            schedule=AgentSchedule(mode=ScheduleMode.CONTINUOUS, interval_seconds=30),
        )
    ]
    t0 = datetime(2026, 8, 27, 12, 0, tzinfo=timezone.utc)
    sched = Scheduler(
        definitions=agents,
        state_store=JsonStateStore(state_path),
        runner=lambda _a: None,
        clock=lambda: t0,
    )
    sched.start("loop", now=t0)
    sched.tick(now=t0)

    overdue = t0 + timedelta(seconds=45)
    restarted = Scheduler(
        definitions=agents,
        state_store=JsonStateStore(state_path),
        runner=lambda _a: None,
        clock=lambda: overdue,
    )
    row = restarted.status()[0]
    assert row.pending is True
    assert row.next_run_at == overdue
    outcomes = restarted.tick(now=overdue)
    assert len(outcomes) == 1 and outcomes[0].ok


@pytest.mark.unit
def test_lifecycle_pause_resume_stop(tmp_path: Path) -> None:
    agents = [
        AgentDefinition(
            name="a",
            schedule=AgentSchedule(mode=ScheduleMode.CONTINUOUS, interval_seconds=5),
        )
    ]
    sched = Scheduler(
        definitions=agents,
        state_store=JsonStateStore(tmp_path / "s.json"),
        runner=lambda _a: None,
    )
    t0 = datetime(2026, 1, 1, 0, 0, tzinfo=timezone.utc)
    sched.start("a", now=t0)
    sched.pause("a")
    assert sched.tick(now=t0) == []
    sched.resume("a", now=t0 + timedelta(seconds=1))
    assert len(sched.tick(now=t0 + timedelta(seconds=1))) == 1
    sched.stop("a")
    assert sched.status()[0].lifecycle is LifecycleState.STOPPED
    assert sched.tick(now=t0 + timedelta(seconds=10)) == []


@pytest.mark.unit
def test_cli_schedule_status(tmp_path: Path, capsys: pytest.CaptureFixture[str]) -> None:
    agents_dir = tmp_path / "agents"
    agents_dir.mkdir()
    (agents_dir / "demo.yaml").write_text(
        "name: demo\nschedule:\n  mode: continuous\n  interval_seconds: 15\n",
        encoding="utf-8",
    )
    state = tmp_path / "state.json"
    from digiclaw.cli import main

    assert main(["schedule", "status", "--agents-dir", str(agents_dir), "--state", str(state)]) == 0
    out = capsys.readouterr().out
    assert "demo" in out
    assert "continuous" in out

    assert (
        main(["schedule", "start", "demo", "--agents-dir", str(agents_dir), "--state", str(state)])
        == 0
    )
    assert main(["schedule", "status", "--agents-dir", str(agents_dir), "--state", str(state)]) == 0
    out2 = capsys.readouterr().out
    assert "running" in out2


@pytest.mark.unit
def test_load_packaged_example_agents() -> None:
    root = Path(__file__).resolve().parents[2] / "digiclaw" / "agents"
    agents = load_agent_definitions(root)
    names = {a.name for a in agents}
    assert "example-cron" in names
    assert "example-continuous" in names


@pytest.mark.unit
def test_unknown_agent_raises_structured_error(tmp_path: Path) -> None:
    sched = Scheduler(
        definitions=[],
        state_store=JsonStateStore(tmp_path / "s.json"),
    )
    with pytest.raises(SchedulerError) as exc:
        sched.start("missing")
    assert exc.value.code == "agent_not_found"


@pytest.mark.unit
def test_duplicate_agent_names_rejected(tmp_path: Path) -> None:
    agents_dir = tmp_path / "agents"
    agents_dir.mkdir()
    (agents_dir / "a.yaml").write_text(
        "name: same\nschedule:\n  mode: continuous\n  interval_seconds: 1\n",
        encoding="utf-8",
    )
    (agents_dir / "b.yaml").write_text(
        "name: same\nschedule:\n  mode: continuous\n  interval_seconds: 2\n",
        encoding="utf-8",
    )
    with pytest.raises(ScheduleSchemaError) as exc:
        load_agent_definitions(agents_dir)
    assert exc.value.code == "duplicate_agent_name"


@pytest.mark.unit
def test_parse_cron_month_names_and_dow_sunday_alias() -> None:
    cron = parse_cron("0 0 1 JAN,FEB 0,7")
    assert cron.month == frozenset({1, 2})
    # 0 and 7 both mean Sunday after normalize.
    assert cron.day_of_week == frozenset({0})


@pytest.mark.unit
def test_parse_cron_rejects_zero_step_and_out_of_range() -> None:
    with pytest.raises(CronParseError) as step_exc:
        parse_cron("*/0 * * * *")
    assert step_exc.value.code == "cron_invalid"

    with pytest.raises(CronParseError) as range_exc:
        parse_cron("60 * * * *")
    assert range_exc.value.code == "cron_invalid"


@pytest.mark.unit
def test_cron_matches_dom_or_dow_when_both_constrained() -> None:
    # 15th of month OR Monday — classic cron OR semantics.
    cron = parse_cron("0 9 15 * MON")
    monday = datetime(2026, 8, 31, 9, 0, tzinfo=timezone.utc)  # Monday, not 15th
    fifteenth = datetime(2026, 8, 15, 9, 0, tzinfo=timezone.utc)  # Saturday
    tuesday = datetime(2026, 8, 25, 9, 0, tzinfo=timezone.utc)  # neither
    assert cron.matches(monday) is True
    assert cron.matches(fifteenth) is True
    assert cron.matches(tuesday) is False


@pytest.mark.unit
def test_next_cron_time_accepts_naive_datetime_as_utc() -> None:
    after = datetime(2026, 8, 27, 12, 0)  # naive → treated as UTC
    nxt = next_cron_time("0 13 * * *", after=after)
    assert nxt == datetime(2026, 8, 27, 13, 0, tzinfo=timezone.utc)


@pytest.mark.unit
def test_event_schedule_requires_event_name() -> None:
    with pytest.raises(ValidationError):
        AgentSchedule(mode=ScheduleMode.EVENT)
    sched = AgentSchedule(mode=ScheduleMode.EVENT, event_name="order.filled")
    assert sched.event_name == "order.filled"


@pytest.mark.unit
def test_cron_schedule_rejects_blank_cron_after_strip() -> None:
    with pytest.raises(ValidationError):
        AgentSchedule(mode=ScheduleMode.CRON, cron="   ")


@pytest.mark.unit
def test_load_agent_definitions_missing_dir(tmp_path: Path) -> None:
    with pytest.raises(ScheduleSchemaError) as exc:
        load_agent_definitions(tmp_path / "missing")
    assert exc.value.code == "agents_dir_missing"


@pytest.mark.unit
def test_scheduler_rejects_disabled_and_event_start(tmp_path: Path) -> None:
    agents = [
        AgentDefinition(
            name="off",
            schedule=AgentSchedule(
                mode=ScheduleMode.CONTINUOUS, interval_seconds=5, enabled=False
            ),
        ),
        AgentDefinition(
            name="evt",
            schedule=AgentSchedule(mode=ScheduleMode.EVENT, event_name="ping"),
        ),
    ]
    sched = Scheduler(
        definitions=agents,
        state_store=JsonStateStore(tmp_path / "s.json"),
        runner=lambda _a: None,
    )
    with pytest.raises(SchedulerError) as disabled:
        sched.start("off")
    assert disabled.value.code == "agent_disabled"

    with pytest.raises(SchedulerError) as event_mode:
        sched.start("evt")
    assert event_mode.value.code == "event_mode_unsupported"


@pytest.mark.unit
def test_scheduler_drops_stale_agent_state_on_restore(tmp_path: Path) -> None:
    state_path = tmp_path / "state.json"
    t0 = datetime(2026, 8, 27, 12, 0, tzinfo=timezone.utc)
    first = [
        AgentDefinition(
            name="gone",
            schedule=AgentSchedule(mode=ScheduleMode.CONTINUOUS, interval_seconds=10),
        ),
        AgentDefinition(
            name="kept",
            schedule=AgentSchedule(mode=ScheduleMode.CONTINUOUS, interval_seconds=10),
        ),
    ]
    sched = Scheduler(
        definitions=first,
        state_store=JsonStateStore(state_path),
        runner=lambda _a: None,
        clock=lambda: t0,
    )
    sched.start("gone", now=t0)
    sched.start("kept", now=t0)

    restarted = Scheduler(
        definitions=[
            AgentDefinition(
                name="kept",
                schedule=AgentSchedule(mode=ScheduleMode.CONTINUOUS, interval_seconds=10),
            )
        ],
        state_store=JsonStateStore(state_path),
        runner=lambda _a: None,
        clock=lambda: t0,
    )
    names = {row.name for row in restarted.status()}
    assert names == {"kept"}
    persisted = JsonStateStore(state_path).load()
    assert "gone" not in persisted.agents
    assert "kept" in persisted.agents
