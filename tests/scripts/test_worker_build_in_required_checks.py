"""The Worker dry-run build must gate merge via the required-checks aggregator.

`wrangler deploy --dry-run` on any Worker blocks merge to develop through the
existing `Required checks passed` aggregator. No new required context, no
branch-protection change: the `worker-build` job lives in ci.yml, is
path-gated on the `workers` changes output, and sits in `required-checks`
`needs:` so a red build fails the one stable required name. The standalone
`build-cloudflare-workers.yml` is gone; its job moved here, not duplicated.
"""

from __future__ import annotations

from pathlib import Path
from typing import Any  # score:allow untyped any — parsed YAML documents

import pytest
import yaml

pytestmark = pytest.mark.unit

REPO_ROOT = Path(__file__).resolve().parents[2]
CI_YML = REPO_ROOT / ".github" / "workflows" / "ci.yml"
STANDALONE = REPO_ROOT / ".github" / "workflows" / "build-cloudflare-workers.yml"


def _ci() -> dict[str, Any]:
    parsed = yaml.safe_load(CI_YML.read_text(encoding="utf-8"))
    assert isinstance(parsed, dict)
    return parsed


def test_worker_build_job_exists() -> None:
    assert "worker-build" in _ci()["jobs"], "ci.yml has no worker-build job"


def test_required_checks_needs_worker_build() -> None:
    needs = _ci()["jobs"]["required-checks"]["needs"]
    assert "worker-build" in needs, "required-checks needs does not contain worker-build"


def test_worker_build_gated_on_workers_output() -> None:
    job = _ci()["jobs"]["worker-build"]
    needs = job.get("needs")
    needs_list = [needs] if isinstance(needs, str) else list(needs or [])
    assert "changes" in needs_list, "worker-build must need the changes job"
    assert "needs.changes.outputs.workers" in str(job.get("if", "")), (
        "worker-build must be if-gated on the workers changes output"
    )


def test_standalone_workflow_deleted() -> None:
    assert not STANDALONE.exists(), "build-cloudflare-workers.yml still exists"
