"""Pin the develop merge rule after DCO sign-off was dropped (DIG-3845).

Chris dropped DCO on 15 Oct 2026. CONTRIBUTING must say sign-off is not
required, and the retired GitHub Actions workflow must stay deleted and
out of the policy inventory. A wording change that brings the sign-off
gate back fails these tests.
"""

from __future__ import annotations

from pathlib import Path

import pytest
import yaml

pytestmark = pytest.mark.unit

REPO_ROOT = Path(__file__).resolve().parents[2]
CONTRIBUTING = REPO_ROOT / "CONTRIBUTING.md"
INVENTORY = REPO_ROOT / ".github" / "policy-checks.yml"
WORKFLOW = REPO_ROOT / ".github" / "workflows" / "ci-dco-sign-off.yml"
MERGE_HEADING = "## Develop merge rule (Chris, 15 Oct 2026)"


def _merge_section() -> str:
    text = CONTRIBUTING.read_text(encoding="utf-8")
    assert MERGE_HEADING in text, "the develop merge rule section is missing"
    section = text.split(MERGE_HEADING, 1)[1]
    tail = section.split("\n## ", 1)
    return tail[0]


def test_merge_rule_drops_dco_sign_off() -> None:
    """Sign-off is named only as something that is no longer required."""
    section = _merge_section()
    assert "DCO sign-off is dropped entirely" in section
    assert "never gate on them" in section
    assert "git commit -s" not in section
    assert "the CI check enforces this" not in section
    assert "All commits signed off" not in section


def test_retired_gha_dco_workflow_stays_gone_and_uninventoried() -> None:
    """Deletion is pinned: the file, the tracked entry, and the check entry."""
    assert not WORKFLOW.is_file(), "ci-dco-sign-off.yml was re-added"
    doc = yaml.safe_load(INVENTORY.read_text(encoding="utf-8"))
    tracked = doc.get("tracked_workflows", [])
    assert "ci-dco-sign-off.yml" not in tracked
    contexts = [c.get("context") for c in doc.get("checks", [])]
    assert "All commits signed off" not in contexts
    workflows = [c.get("workflow") for c in doc.get("checks", [])]
    assert "ci-dco-sign-off.yml" not in workflows
