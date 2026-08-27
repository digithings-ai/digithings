"""Minimal schedule schema for digiclaw agent YAML definitions.

Full agent registry (#217) owns name/tools/output_sink later. This module only
models the schedule block the scheduler needs, plus a thin wrapper so YAML files
remain loadable once the registry lands.
"""

from __future__ import annotations

from enum import Enum
from pathlib import Path

import yaml
from pydantic import BaseModel, Field, ValidationError, field_validator, model_validator


class ScheduleMode(str, Enum):
    """How an agent is triggered."""

    CRON = "cron"
    CONTINUOUS = "continuous"
    EVENT = "event"


class AgentSchedule(BaseModel):
    """Schedule block inside an agent definition YAML."""

    mode: ScheduleMode
    cron: str | None = Field(
        default=None,
        description="Standard 5-field cron expression when mode=cron.",
    )
    interval_seconds: int | None = Field(
        default=None,
        ge=1,
        description="Sleep between iterations when mode=continuous.",
    )
    enabled: bool = True
    event_name: str | None = Field(
        default=None,
        description="Event name when mode=event (trigger wiring deferred).",
    )

    @field_validator("cron")
    @classmethod
    def _strip_cron(cls, value: str | None) -> str | None:
        if value is None:
            return None
        stripped = value.strip()
        return stripped or None

    @model_validator(mode="after")
    def _require_mode_fields(self) -> AgentSchedule:
        if self.mode is ScheduleMode.CRON:
            if not self.cron:
                raise ValueError("schedule.cron is required when mode=cron")
        elif self.mode is ScheduleMode.CONTINUOUS:
            if self.interval_seconds is None:
                raise ValueError("schedule.interval_seconds is required when mode=continuous")
        elif self.mode is ScheduleMode.EVENT:
            if not (self.event_name and self.event_name.strip()):
                raise ValueError("schedule.event_name is required when mode=event")
        return self


class AgentDefinition(BaseModel):
    """Minimal agent definition — schedule-focused until #217 lands."""

    name: str = Field(..., min_length=1)
    description: str = ""
    schedule: AgentSchedule

    @field_validator("name")
    @classmethod
    def _normalize_name(cls, value: str) -> str:
        name = value.strip()
        if not name:
            raise ValueError("agent name must not be empty")
        return name


class ScheduleSchemaError(ValueError):
    """Structured validation/load error for schedule YAML."""

    def __init__(self, code: str, message: str) -> None:
        self.code = code
        self.message = message
        super().__init__(f"{code}: {message}")


def load_agent_definition(path: Path) -> AgentDefinition:
    """Parse and validate one agent YAML file."""
    try:
        raw = yaml.safe_load(path.read_text(encoding="utf-8"))
    except OSError as exc:
        raise ScheduleSchemaError("schedule_yaml_read_failed", str(exc)) from exc
    except yaml.YAMLError as exc:
        raise ScheduleSchemaError("schedule_yaml_invalid", f"{path}: {exc}") from exc

    if not isinstance(raw, dict):
        raise ScheduleSchemaError(
            "schedule_yaml_invalid",
            f"{path}: expected a mapping at document root",
        )

    data: dict[str, Any] = dict(raw)
    if "name" not in data:
        data["name"] = path.stem

    try:
        return AgentDefinition.model_validate(data)
    except ValidationError as exc:
        raise ScheduleSchemaError("schedule_schema_invalid", f"{path}: {exc}") from exc


def load_agent_definitions(agents_dir: Path) -> list[AgentDefinition]:
    """Load ``*.yml`` / ``*.yaml`` definitions from *agents_dir* (sorted by name)."""
    if not agents_dir.is_dir():
        raise ScheduleSchemaError(
            "agents_dir_missing",
            f"agents directory not found: {agents_dir}",
        )

    paths = sorted(
        {*agents_dir.glob("*.yml"), *agents_dir.glob("*.yaml")},
        key=lambda p: p.name.lower(),
    )
    agents = [load_agent_definition(path) for path in paths]
    names = [a.name for a in agents]
    dupes = {n for n in names if names.count(n) > 1}
    if dupes:
        raise ScheduleSchemaError(
            "duplicate_agent_name",
            f"duplicate agent name(s): {', '.join(sorted(dupes))}",
        )
    return agents
