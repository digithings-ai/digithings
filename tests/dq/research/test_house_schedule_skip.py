"""Skip later house crons once today's pipeline already succeeded (#FX Hub retry)."""

from __future__ import annotations

import importlib.util
import sys
from datetime import UTC, date, datetime
from pathlib import Path
from types import ModuleType

import pytest

pytestmark = pytest.mark.unit

_SCRIPT = (
    Path(__file__).resolve().parents[3]
    / "digiquant"
    / "scripts"
    / "research"
    / "house_schedule_skip.py"
)


def _load() -> ModuleType:
    spec = importlib.util.spec_from_file_location("house_schedule_skip", _SCRIPT)
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


def _run(
    module: ModuleType,
    *,
    run_id: int,
    created_at: datetime,
    status: str = "completed",
    conclusion: str | None = "success",
    event: str = "schedule",
) -> object:
    return module.PriorRun(
        run_id=run_id,
        status=status,
        conclusion=conclusion,
        created_at=created_at,
        event=event,
    )


def test_skips_when_another_success_exists_on_run_date() -> None:
    module = _load()
    prior = _run(module, run_id=1, created_at=datetime(2026, 9, 1, 9, 20, tzinfo=UTC))
    assert (
        module.should_skip_house_run(
            current_run_id=2,
            run_date=date(2026, 9, 1),
            runs=(prior,),
        )
        is True
    )


def test_does_not_skip_when_only_failures_exist() -> None:
    module = _load()
    prior = _run(
        module,
        run_id=1,
        created_at=datetime(2026, 9, 1, 9, 20, tzinfo=UTC),
        conclusion="failure",
    )
    assert (
        module.should_skip_house_run(
            current_run_id=2,
            run_date=date(2026, 9, 1),
            runs=(prior,),
        )
        is False
    )


def test_does_not_skip_yesterday_or_the_current_run() -> None:
    module = _load()
    yesterday = _run(module, run_id=1, created_at=datetime(2026, 8, 31, 21, 41, tzinfo=UTC))
    self_run = _run(module, run_id=9, created_at=datetime(2026, 9, 1, 10, 17, tzinfo=UTC))
    assert (
        module.should_skip_house_run(
            current_run_id=9,
            run_date=date(2026, 9, 1),
            runs=(yesterday, self_run),
        )
        is False
    )


def test_parse_runs_reads_gh_run_list_json() -> None:
    module = _load()
    parsed = module.parse_runs(
        [
            {
                "databaseId": 11,
                "status": "completed",
                "conclusion": "success",
                "createdAt": "2026-09-01T09:20:00Z",
                "event": "schedule",
            },
            {"databaseId": "nope"},
            {
                "databaseId": 12,
                "status": "completed",
                "conclusion": "success",
                "createdAt": "2026-09-01T09:21:00Z",
            },
        ]
    )
    assert len(parsed) == 1
    assert parsed[0].run_id == 11
    assert parsed[0].created_at.tzinfo is not None
    assert parsed[0].event == "schedule"


def test_workflow_dispatch_success_does_not_skip() -> None:
    module = _load()
    prior = _run(
        module,
        run_id=1,
        created_at=datetime(2026, 9, 1, 9, 20, tzinfo=UTC),
        event="workflow_dispatch",
    )
    assert (
        module.should_skip_house_run(
            current_run_id=2,
            run_date=date(2026, 9, 1),
            runs=(prior,),
        )
        is False
    )


def test_workflow_dispatch_force_never_skips() -> None:
    module = _load()
    prior = _run(module, run_id=1, created_at=datetime(2026, 9, 1, 9, 20, tzinfo=UTC))
    assert (
        module.should_skip_house_run(
            current_run_id=2,
            run_date=date(2026, 9, 1),
            runs=(prior,),
            force=True,
        )
        is False
    )
