"""Regression tests for the Atlas Activity repair script paths (#1928)."""

from __future__ import annotations

import importlib.util
from datetime import datetime, timezone
from pathlib import Path
from types import ModuleType

import pytest

pytestmark = pytest.mark.unit

_SCRIPT_DIR = Path(__file__).resolve().parents[3] / "digiquant" / "scripts" / "atlas"


def _load_script(name: str) -> ModuleType:
    path = _SCRIPT_DIR / f"{name}.py"
    spec = importlib.util.spec_from_file_location(name, path)
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


@pytest.mark.parametrize(
    ("script_name", "children"),
    [
        (
            "backfill_position_events",
            ["execute_at_open.py", "backfill_execution_prices.py"],
        ),
        (
            "ensure_position_activity_through_today",
            [
                "refresh_performance_metrics.py",
                "backfill_position_events.py",
                "reconcile_position_events_from_positions.py",
            ],
        ),
    ],
)
def test_activity_wrappers_resolve_existing_sibling_scripts(
    script_name: str, children: list[str]
) -> None:
    module = _load_script(script_name)

    script_dir = module._script_dir()

    assert script_dir == _SCRIPT_DIR
    assert all((script_dir / child).is_file() for child in children)


@pytest.mark.parametrize(
    ("now_utc", "schedule", "expected"),
    [
        ("2026-08-05T13:20:00+00:00", "35 13 * * MON-FRI", False),
        ("2026-08-05T13:35:00+00:00", "35 13 * * MON-FRI", True),
        ("2026-08-05T15:41:00+00:00", "35 13 * * MON-FRI", True),
        ("2026-08-05T15:41:00+00:00", "35 14 * * MON-FRI", False),
        ("2026-01-05T14:35:00+00:00", "35 14 * * MON-FRI", True),
        ("2026-01-05T15:35:00+00:00", "35 13 * * MON-FRI", False),
    ],
)
def test_market_open_gate_selects_the_seasonal_cron_and_allows_delay(
    now_utc: str, schedule: str, expected: bool
) -> None:
    module = _load_script("market_open_gate")

    actual = module.should_run_at_open(
        now=datetime.fromisoformat(now_utc).astimezone(timezone.utc),
        schedule=schedule,
    )

    assert actual is expected


def test_market_open_gate_allows_manual_dispatch() -> None:
    module = _load_script("market_open_gate")

    assert module.should_run_at_open(
        now=datetime.fromisoformat("2026-08-05T12:00:00+00:00"),
        schedule="",
        force=True,
    )


def test_market_open_gate_treats_naive_replay_timestamp_as_utc() -> None:
    module = _load_script("market_open_gate")

    assert module.parse_utc("2026-08-05T13:35:00") == datetime(
        2026, 8, 5, 13, 35, tzinfo=timezone.utc
    )
