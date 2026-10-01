"""Pin: develop GHA has no on.schedule. Clocks live on digithings-cron.

Leftover sweep after #4970 / #4967 / #3579: every production cron GitHub used
to own on this repo is either a Cloudflare Cron Trigger (apps/digithings-cron)
or a manual dispatch. Re-adding ``schedule:`` on develop would double-fire
with the Worker (default branch is develop).
"""

from __future__ import annotations

import re
from pathlib import Path

import pytest
import yaml

pytestmark = pytest.mark.unit

REPO_ROOT = Path(__file__).resolve().parents[2]
WORKFLOW_DIR = REPO_ROOT / ".github" / "workflows"
JOBS_SOURCE = REPO_ROOT / "apps" / "digithings-cron" / "src" / "jobs.ts"


def _on(doc: dict) -> object:
    if "on" in doc:
        return doc["on"]
    if True in doc:
        return doc[True]
    raise AssertionError("workflow missing on:")


def _schedule_offenders() -> list[str]:
    offenders: list[str] = []
    for path in sorted(WORKFLOW_DIR.glob("*.yml")):
        on = _on(yaml.safe_load(path.read_text(encoding="utf-8")))
        if isinstance(on, dict) and "schedule" in on:
            offenders.append(path.name)
        elif on == "schedule":
            offenders.append(path.name)
        elif isinstance(on, list) and "schedule" in on:
            offenders.append(path.name)
    return offenders


def test_develop_workflows_have_no_gha_schedule() -> None:
    assert _schedule_offenders() == []


def test_jobs_map_does_not_claim_a_digisearch_parity_clock() -> None:
    """digisearch_parity is not a workflow in this repo. Do not invent a cron."""
    text = JOBS_SOURCE.read_text(encoding="utf-8")
    ids = re.findall(r'(?:wd|rd|cj|pj)\(\s*"([^"]+)"', text)
    workflows = re.findall(r'(?:wd|rd|cj|pj)\([^)]*?"([^"]+\.yml)"', text, flags=re.DOTALL)
    assert "digisearch_parity" not in ids
    assert "digisearch-parity" not in ids
    assert "digisearch_parity.yml" not in workflows
    assert "digisearch-parity.yml" not in workflows
