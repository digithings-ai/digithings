"""Pin the CONTRIBUTING DCO gate wording to `local-ci` (DIG-3683).

Develop branch protection requires exactly the `local-ci` status context,
which enforces the DCO 1.1 sign-off. The retired GHA workflow
`ci-dco-sign-off.yml` no longer runs, so CONTRIBUTING must name `local-ci`
as the enforcing gate — and must not re-name a dead gate. A wording change
that drops the `local-ci` name, or reinstates a retired gate name as the
enforcer, fails these tests.
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
DCO_HEADING = "## Contributor terms — DCO 1.1"


def _dco_section() -> str:
    text = CONTRIBUTING.read_text(encoding="utf-8")
    assert DCO_HEADING in text, "the DCO 1.1 section is missing from CONTRIBUTING.md"
    section = text.split(DCO_HEADING, 1)[1]
    # The section runs to the next top-level heading or EOF.
    tail = section.split("\n## ", 1)
    return tail[0]


def test_dco_section_names_local_ci_as_the_enforcing_gate() -> None:
    """The doc names the check developers actually see fail."""
    section = _dco_section()
    assert "local-ci" in section


def test_dco_section_does_not_name_a_retired_gate_as_enforcer() -> None:
    """A future edit cannot re-name a dead gate without failing here."""
    section = _dco_section()
    assert "the CI check enforces this" not in section
    assert "Required checks passed" not in section
    assert "All commits signed off" not in section


def test_retired_gha_dco_workflow_stays_gone_and_uninventoried() -> None:
    """Deletion is pinned: the file, the tracked entry, and the check entry."""
    assert not WORKFLOW.is_file(), "ci-dco-sign-off.yml was re-added; DCO lives in local-ci"
    doc = yaml.safe_load(INVENTORY.read_text(encoding="utf-8"))
    tracked = doc.get("tracked_workflows", [])
    assert "ci-dco-sign-off.yml" not in tracked
    contexts = [c.get("context") for c in doc.get("checks", [])]
    assert "All commits signed off" not in contexts
    workflows = [c.get("workflow") for c in doc.get("checks", [])]
    assert "ci-dco-sign-off.yml" not in workflows
