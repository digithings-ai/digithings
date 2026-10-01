"""Pin the gold-enrichment refresh workflow shape (#4804)."""

from __future__ import annotations

from pathlib import Path

import pytest
import yaml

pytestmark = pytest.mark.unit


def _workflow() -> dict:
    path = Path(__file__).resolve().parents[2] / ".github" / "workflows" / "enrich-gold-refresh.yml"
    return yaml.safe_load(path.read_text(encoding="utf-8"))


def test_workflow_has_weekly_schedule_and_dispatch() -> None:
    wf = _workflow()
    triggers = wf[True]  # PyYAML parses `on:` as boolean True
    assert "workflow_dispatch" in triggers
    schedules = triggers["schedule"]
    assert any("cron" in entry for entry in schedules)


def test_workflow_runs_refresh_script_offline_safe() -> None:
    wf = _workflow()
    steps = [step for job in wf["jobs"].values() for step in job["steps"]]
    run_steps = [s.get("run", "") for s in steps if "run" in s]
    assert any("refresh_gold_enrichment.py" in cmd for cmd in run_steps)
    assert not any("GLOOMBERB_SESSION_COOKIE" in cmd for cmd in run_steps)
