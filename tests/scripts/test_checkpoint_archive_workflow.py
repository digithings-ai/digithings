"""Pin pipeline-checkpoint-archive.yml spec (issues #3761, #3766)."""

from __future__ import annotations

from pathlib import Path

import pytest
import yaml

pytestmark = pytest.mark.unit

WORKFLOW = (
    Path(__file__).resolve().parents[2]
    / ".github"
    / "workflows"
    / "pipeline-checkpoint-archive.yml"
)


def _load() -> dict:
    return yaml.safe_load(WORKFLOW.read_text(encoding="utf-8"))


def test_schedule_and_dispatch() -> None:
    spec = _load()
    on = spec[True]  # YAML 1.1 parses the `on:` key as boolean True
    assert "workflow_dispatch" in on
    assert "30 13 * * *" in [entry["cron"] for entry in on["schedule"]]


def test_secrets_wired() -> None:
    env = _load()["jobs"]["archive"]["env"]
    for name in (
        "CORE_SUPABASE_URL",
        "CORE_SUPABASE_SERVICE_KEY",
        "R2_ACCOUNT_ID",
        "R2_BUCKET",
        "R2_ACCESS_KEY_ID",
        "R2_SECRET_ACCESS_KEY",
        "CORE_POSTGRES_URI",
    ):
        assert name in env, name
    for old in (
        "CHECKPOINT_ARCHIVE_R2_ENDPOINT",
        "CHECKPOINT_ARCHIVE_R2_BUCKET",
        "CHECKPOINT_ARCHIVE_R2_ACCESS_KEY",
        "CHECKPOINT_ARCHIVE_R2_SECRET_KEY",
    ):
        assert old not in env, old


def test_runs_archiver_with_retention() -> None:
    steps = _load()["jobs"]["archive"]["steps"]
    runs = [s.get("run", "") for s in steps]
    assert any(
        "scripts/digiquant_archive_checkpoints.py" in r and "--retain-days 1" in r for r in runs
    )
