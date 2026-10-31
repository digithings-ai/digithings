"""Path A trap YAML restored after #4919/#4967 — dispatch-only, CF owns clocks."""

from __future__ import annotations

from pathlib import Path

import pytest
import yaml

pytestmark = pytest.mark.unit

WORKFLOW_DIR = Path(__file__).resolve().parents[2] / ".github" / "workflows"

TRAPS = (
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


def test_wrangler_lists_path_a_trap_crons() -> None:
    wrangler = (
        Path(__file__).resolve().parents[2]
        / "apps"
        / "digithings-cron"
        / "wrangler.toml"
    ).read_text(encoding="utf-8")
    for cron in ("13 6 * * MON", "10 6 * * MON", "23 9 * * *"):
        assert f'"{cron}"' in wrangler, cron


def test_wrangler_drops_the_github_locked_trap_cron() -> None:
    """DIG-4364: four clocks are held off because their workflows are
    `disabled_manually` on GitHub since the 2026-10-14 cost lock, so each cron
    line must be gone from wrangler.toml — the trigger would answer 422 on every
    tick. The JOBS rows keep their cron so restoring a lane is a one-flag edit
    once the workflow is re-enabled. `agent-pr-finalizer` (07:11) was a Path A
    trap; its workflow and row are deleted, and its cron must stay off too. The
    others are listed so the wrangler side stays in step with `jobs.test.ts`'s
    GITHUB_LOCK_DISABLED_IDS."""
    wrangler = (
        Path(__file__).resolve().parents[2]
        / "apps"
        / "digithings-cron"
        / "wrangler.toml"
    ).read_text(encoding="utf-8")
    for cron in ("11 7 * * *", "21 6 * * *", "33 6 * * MON", "37 6 * * MON"):
        assert f'"{cron}"' not in wrangler, cron
