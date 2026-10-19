"""Pin the gold-enrichment refresh workflow shape (#4804)."""

from __future__ import annotations

from pathlib import Path

import pytest
import yaml

pytestmark = pytest.mark.unit


def _workflow() -> dict:
    path = Path(__file__).resolve().parents[2] / ".github" / "workflows" / "enrich-gold-refresh.yml"
    return yaml.safe_load(path.read_text(encoding="utf-8"))


def test_workflow_is_dispatch_only() -> None:
    """The weekly clock was dropped in DIG-4464: develop carries no GHA `schedule:`."""
    wf = _workflow()
    triggers = wf[True]  # PyYAML parses `on:` as boolean True
    assert "workflow_dispatch" in triggers
    assert "schedule" not in triggers


def test_workflow_runs_refresh_script_offline_safe() -> None:
    wf = _workflow()
    steps = [step for job in wf["jobs"].values() for step in job["steps"]]
    run_steps = [s.get("run", "") for s in steps if "run" in s]
    assert any("refresh_gold_enrichment.py" in cmd for cmd in run_steps)
    assert not any("GLOOMBERB_SESSION_COOKIE" in cmd for cmd in run_steps)
