"""Repo inventory the canonical env names depend on (#4295).

The env-lookup contract lives in ``test_envcompat.py``. What is checked here
is the repository side of that contract: the operator scripts carry the
``digiquant_`` prefix and the cron probe workflow still names the house
pipeline separately.
"""

from __future__ import annotations

from pathlib import Path

import pytest

pytestmark = pytest.mark.unit

REPO_ROOT = Path(__file__).resolve().parents[3]


def test_operator_scripts_use_digiquant_prefix() -> None:
    scripts = REPO_ROOT / "scripts"
    expected = (
        "digiquant_cron_check.py",
        "digiquant_route_cron.py",
        "digiquant_staging_e2e.py",
        "digiquant_house_pipeline_proof.py",
        "digiquant_pages_dashboard_gate.py",
        "digiquant_seal_byok.py",
        "digiquant_apply_vendor_secrets.py",
    )
    for name in expected:
        assert (scripts / name).is_file(), name
    # GHA ``execution-cron-check.yml`` is protected on cursor/*; wrapper stays until
    # a feat/ hop renames the workflow.
    leftover = [
        p.name for p in scripts.glob("execution_*.py") if p.name != "execution_cron_check.py"
    ]
    assert leftover == [], leftover
    assert (scripts / "execution_cron_check.py").is_file()


def test_cron_probe_workflow_keeps_house_pipeline_separate() -> None:
    installed = REPO_ROOT / ".github" / "workflows" / "execution-cron-check.yml"
    spec = (
        REPO_ROOT
        / "docs"
        / "agent-backlog"
        / "execution-tenancy"
        / "kairos-cron-check.workflow.yml"
    )
    assert installed.is_file()
    assert spec.is_file()
    blob = installed.read_text(encoding="utf-8")
    assert "pipeline-digiquant.yml" in blob
    assert "scripts/execution_cron_check.py" in blob or "scripts/digiquant_cron_check.py" in blob
