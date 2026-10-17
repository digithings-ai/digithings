"""Path A trap YAML restored after #4919/#4967 — dispatch-only, CF owns clocks."""

from __future__ import annotations

from pathlib import Path

import pytest
import yaml

pytestmark = pytest.mark.unit

WORKFLOW_DIR = Path(__file__).resolve().parents[2] / ".github" / "workflows"

TRAPS = (
    ("agent-pr-finalizer.yml", "Agent: PR finalizer"),
    ("agent-backlog-snapshot.yml", "Agent: backlog snapshot"),
    ("refresh-repo-activity.yml", "Refresh: repo activity snapshot"),
    ("project-enforce-assignment.yml", "Project: enforce assignment"),
)


def _on(doc: dict) -> dict:
    raw = doc.get("on", doc.get(True))
    assert isinstance(raw, dict), "workflow missing on:"
    return raw


@pytest.mark.parametrize(("filename", "name"), TRAPS)
def test_path_a_trap_is_dispatch_only(filename: str, name: str) -> None:
    path = WORKFLOW_DIR / filename
    assert path.is_file(), filename
    doc = yaml.safe_load(path.read_text(encoding="utf-8"))
    assert doc["name"] == name
    on = _on(doc)
    assert "workflow_dispatch" in on
    assert "schedule" not in on


def test_agent_pr_finalizer_defaults_dry_run_true() -> None:
    """CF must send dry_run=false; the workflow default is report-only."""
    doc = yaml.safe_load(
        (WORKFLOW_DIR / "agent-pr-finalizer.yml").read_text(encoding="utf-8")
    )
    dry_run = _on(doc)["workflow_dispatch"]["inputs"]["dry_run"]
    assert dry_run["default"] == "true"


def test_wrangler_lists_path_a_trap_crons() -> None:
    wrangler = (
        Path(__file__).resolve().parents[2]
        / "apps"
        / "digithings-cron"
        / "wrangler.toml"
    ).read_text(encoding="utf-8")
    for cron in ("11 7 * * *", "13 6 * * MON", "10 6 * * MON", "23 9 * * *"):
        assert f'"{cron}"' in wrangler, cron
