"""digiclaw agent scheduler — cron, continuous, lifecycle, restart persistence.

Owns start/stop/pause/resume for scheduled agents. Agent execution is injected via
``AgentRunner`` so this module stays free of digigraph/OpenClaw coupling until
those runtimes exist. Event-triggered mode is modeled in the schema but not
wired here (#218 acceptance focuses on cron + continuous).
"""

from __future__ import annotations

import json
import os
from collections.abc import Callable, Mapping
from datetime import datetime, timedelta, timezone
from enum import Enum
from pathlib import Path
from typing import Protocol

from pydantic import BaseModel, Field

from digiclaw.cron import CronParseError, next_cron_time, parse_cron
from digiclaw.schedule_schema import (
    AgentDefinition,
    ScheduleMode,
    ScheduleSchemaError,
    load_agent_definitions,
)

AgentRunner = Callable[[AgentDefinition], None]
Clock = Callable[[], datetime]


class LifecycleState(str, Enum):
    """Runtime lifecycle for a scheduled agent."""

    STOPPED = "stopped"
    RUNNING = "running"
    PAUSED = "paused"


class SchedulerError(ValueError):
    """Structured scheduler error with stable ``code``."""

    def __init__(self, code: str, message: str) -> None:
        self.code = code
        self.message = message
        super().__init__(f"{code}: {message}")


class AgentRuntimeState(BaseModel):
    """Persisted per-agent scheduler state."""

    lifecycle: LifecycleState = LifecycleState.STOPPED
    next_run_at: datetime | None = None
    last_run_at: datetime | None = None
    last_status: str | None = None
    last_error: str | None = None
    pending: bool = False


class SchedulerState(BaseModel):
    """On-disk scheduler snapshot (survives process restart)."""

    agents: dict[str, AgentRuntimeState] = Field(default_factory=dict)
    updated_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))


class ScheduleStatusRow(BaseModel):
    """One row for ``digiclaw schedule status``."""

    name: str
    mode: ScheduleMode
    lifecycle: LifecycleState
    enabled: bool
    next_run_at: datetime | None
    last_run_at: datetime | None
    last_status: str | None
    pending: bool
    cron: str | None = None
    interval_seconds: int | None = None
    event_name: str | None = None


class RunOutcome(BaseModel):
    """Result of one isolated agent invocation."""

    name: str
    ok: bool
    error: str | None = None
    ran_at: datetime


class _StateStore(Protocol):
    def load(self) -> SchedulerState: ...

    def save(self, state: SchedulerState) -> None: ...


class JsonStateStore:
    """Atomic JSON file persistence for ``SchedulerState``."""

    def __init__(self, path: Path) -> None:
        self.path = path

    def load(self) -> SchedulerState:
        if not self.path.is_file():
            return SchedulerState()
        try:
            raw = json.loads(self.path.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError) as exc:
            raise SchedulerError("scheduler_state_corrupt", str(exc)) from exc
        return SchedulerState.model_validate(raw)

    def save(self, state: SchedulerState) -> None:
        state.updated_at = datetime.now(timezone.utc)
        self.path.parent.mkdir(parents=True, exist_ok=True)
        payload = state.model_dump(mode="json")
        tmp = self.path.with_suffix(self.path.suffix + ".tmp")
        tmp.write_text(json.dumps(payload, indent=2, sort_keys=True) + "\n", encoding="utf-8")
        tmp.replace(self.path)


def default_agents_dir() -> Path:
    """Resolve agents directory from env or packaged default."""
    env = (os.environ.get("DIGICLAW_AGENTS_DIR") or "").strip()
    if env:
        return Path(env)
    return Path(__file__).resolve().parents[2] / "agents"


def default_state_path() -> Path:
    """Resolve scheduler state path from env or workspace default."""
    env = (os.environ.get("DIGICLAW_SCHEDULER_STATE") or "").strip()
    if env:
        return Path(env)
    workspace = Path(os.environ.get("DIGI_WORKSPACE") or ".")
    return workspace / ".digiclaw" / "scheduler_state.json"


def default_agent_runner(agent: AgentDefinition) -> None:
    """No-op placeholder runner until OpenClaw / digigraph invocation exists."""
    _ = agent


class Scheduler:
    """In-process scheduler with durable lifecycle and next-run state."""

    def __init__(
        self,
        *,
        agents_dir: Path | None = None,
        state_store: JsonStateStore | None = None,
        runner: AgentRunner | None = None,
        definitions: list[AgentDefinition] | None = None,
        clock: Clock | None = None,
    ) -> None:
        self.agents_dir = agents_dir or default_agents_dir()
        self._store = state_store or JsonStateStore(default_state_path())
        self._runner: AgentRunner = runner or default_agent_runner
        self._clock: Clock = clock or (lambda: datetime.now(timezone.utc))
        self._definitions: dict[str, AgentDefinition] = {}
        self._state = SchedulerState()
        if definitions is not None:
            self._set_definitions(definitions)
        else:
            self.reload_definitions()
        self.restore()

    def reload_definitions(self) -> list[AgentDefinition]:
        """Reload YAML definitions from ``agents_dir``."""
        try:
            agents = load_agent_definitions(self.agents_dir)
        except ScheduleSchemaError as exc:
            raise SchedulerError(exc.code, exc.message) from exc
        self._set_definitions(agents)
        return list(self._definitions.values())

    def restore(self) -> None:
        """Load persisted state and re-queue overdue running jobs after restart."""
        self._state = self._store.load()
        now = self._clock()
        changed = False
        for name, agent in self._definitions.items():
            runtime = self._state.agents.get(name)
            if runtime is None:
                self._state.agents[name] = AgentRuntimeState()
                changed = True
                continue
            if runtime.lifecycle is not LifecycleState.RUNNING:
                continue
            if not agent.schedule.enabled:
                continue
            if agent.schedule.mode is ScheduleMode.EVENT:
                continue
            due = runtime.pending or (
                runtime.next_run_at is not None and runtime.next_run_at <= now
            )
            if due:
                runtime.pending = True
                runtime.next_run_at = now
                changed = True
            elif runtime.next_run_at is None:
                runtime.next_run_at = self._compute_next(agent, after=now)
                changed = True
        # Drop state for agents that no longer exist in YAML.
        stale = [n for n in self._state.agents if n not in self._definitions]
        for name in stale:
            del self._state.agents[name]
            changed = True
        if changed:
            self._persist()

    def start(self, name: str, *, now: datetime | None = None) -> AgentRuntimeState:
        """Mark agent running and schedule the next run."""
        agent, runtime = self._require(name)
        if not agent.schedule.enabled:
            raise SchedulerError("agent_disabled", f"agent {name!r} has schedule.enabled=false")
        if agent.schedule.mode is ScheduleMode.EVENT:
            raise SchedulerError(
                "event_mode_unsupported",
                f"agent {name!r} uses event mode; trigger wiring is not implemented yet",
            )
        instant = self._now(now)
        runtime.lifecycle = LifecycleState.RUNNING
        # Continuous: first iteration is immediate; cron: next fire after now.
        if agent.schedule.mode is ScheduleMode.CONTINUOUS:
            runtime.next_run_at = instant
            runtime.pending = True
        else:
            runtime.next_run_at = self._compute_next(agent, after=instant)
            runtime.pending = False
        self._persist()
        return runtime.model_copy(deep=True)

    def stop(self, name: str) -> AgentRuntimeState:
        """Stop agent; clear pending and next run."""
        _, runtime = self._require(name)
        runtime.lifecycle = LifecycleState.STOPPED
        runtime.pending = False
        runtime.next_run_at = None
        self._persist()
        return runtime.model_copy(deep=True)

    def pause(self, name: str) -> AgentRuntimeState:
        """Pause a running agent without clearing last-run metadata."""
        _, runtime = self._require(name)
        if runtime.lifecycle is LifecycleState.STOPPED:
            raise SchedulerError("agent_not_running", f"agent {name!r} is stopped")
        runtime.lifecycle = LifecycleState.PAUSED
        runtime.pending = False
        self._persist()
        return runtime.model_copy(deep=True)

    def resume(self, name: str, *, now: datetime | None = None) -> AgentRuntimeState:
        """Resume a paused agent; overdue work is re-queued immediately."""
        agent, runtime = self._require(name)
        if runtime.lifecycle is not LifecycleState.PAUSED:
            raise SchedulerError("agent_not_paused", f"agent {name!r} is not paused")
        instant = self._now(now)
        runtime.lifecycle = LifecycleState.RUNNING
        if runtime.next_run_at is None or runtime.next_run_at <= instant:
            runtime.next_run_at = instant
            runtime.pending = True
        else:
            # Keep future next_run_at; ensure it is still valid for the mode.
            if agent.schedule.mode is ScheduleMode.CONTINUOUS:
                runtime.next_run_at = instant
                runtime.pending = True
        self._persist()
        return runtime.model_copy(deep=True)

    def status(self) -> list[ScheduleStatusRow]:
        """Return status rows sorted by agent name."""
        rows: list[ScheduleStatusRow] = []
        for name in sorted(self._definitions):
            agent = self._definitions[name]
            runtime = self._state.agents.get(name) or AgentRuntimeState()
            sched = agent.schedule
            rows.append(
                ScheduleStatusRow(
                    name=name,
                    mode=sched.mode,
                    lifecycle=runtime.lifecycle,
                    enabled=sched.enabled,
                    next_run_at=runtime.next_run_at,
                    last_run_at=runtime.last_run_at,
                    last_status=runtime.last_status,
                    pending=runtime.pending,
                    cron=sched.cron,
                    interval_seconds=sched.interval_seconds,
                    event_name=sched.event_name,
                )
            )
        return rows

    def tick(self, *, now: datetime | None = None) -> list[RunOutcome]:
        """Execute every due running agent once; failures stay isolated."""
        instant = self._now(now)
        outcomes: list[RunOutcome] = []
        for name, agent in sorted(self._definitions.items()):
            runtime = self._state.agents.setdefault(name, AgentRuntimeState())
            if runtime.lifecycle is not LifecycleState.RUNNING:
                continue
            if not agent.schedule.enabled:
                continue
            if agent.schedule.mode is ScheduleMode.EVENT:
                continue
            due = runtime.pending or (
                runtime.next_run_at is not None and runtime.next_run_at <= instant
            )
            if not due:
                continue
            outcomes.append(self._run_isolated(agent, runtime, instant))
        if outcomes:
            self._persist()
        return outcomes

    def _run_isolated(
        self,
        agent: AgentDefinition,
        runtime: AgentRuntimeState,
        instant: datetime,
    ) -> RunOutcome:
        """Invoke the runner; never let an exception poison the next schedule."""
        error: str | None = None
        try:
            self._runner(agent)
            ok = True
            runtime.last_status = "ok"
            runtime.last_error = None
        except Exception as exc:
            ok = False
            error = f"{type(exc).__name__}: {exc}"
            runtime.last_status = "error"
            runtime.last_error = error
        runtime.last_run_at = instant
        runtime.pending = False
        runtime.next_run_at = self._compute_next(agent, after=instant)
        return RunOutcome(name=agent.name, ok=ok, error=error, ran_at=instant)

    def _compute_next(self, agent: AgentDefinition, *, after: datetime) -> datetime:
        sched = agent.schedule
        if sched.mode is ScheduleMode.CONTINUOUS:
            if sched.interval_seconds is None:
                raise SchedulerError(
                    "schedule_invalid",
                    f"agent {agent.name!r} continuous schedule missing interval_seconds",
                )
            return after + timedelta(seconds=sched.interval_seconds)
        if sched.mode is ScheduleMode.CRON:
            if not sched.cron:
                raise SchedulerError(
                    "schedule_invalid",
                    f"agent {agent.name!r} cron schedule missing cron expression",
                )
            try:
                parse_cron(sched.cron)
                return next_cron_time(sched.cron, after=after)
            except CronParseError as exc:
                raise SchedulerError(exc.code, exc.message) from exc
        raise SchedulerError(
            "event_mode_unsupported",
            f"cannot compute next run for event-mode agent {agent.name!r}",
        )

    def _require(self, name: str) -> tuple[AgentDefinition, AgentRuntimeState]:
        agent = self._definitions.get(name)
        if agent is None:
            raise SchedulerError("agent_not_found", f"unknown agent {name!r}")
        runtime = self._state.agents.setdefault(name, AgentRuntimeState())
        return agent, runtime

    def _set_definitions(self, agents: list[AgentDefinition]) -> None:
        self._definitions = {a.name: a for a in agents}

    def _persist(self) -> None:
        self._store.save(self._state)

    def _now(self, when: datetime | None) -> datetime:
        if when is None:
            return _utc(self._clock())
        return _utc(when)

    @property
    def definitions(self) -> Mapping[str, AgentDefinition]:
        return dict(self._definitions)


def _utc(when: datetime) -> datetime:
    if when.tzinfo is None:
        return when.replace(tzinfo=timezone.utc)
    return when.astimezone(timezone.utc)
