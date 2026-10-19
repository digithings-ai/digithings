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


def _worker_build_runs() -> list[str]:
    steps = _ci()["jobs"]["worker-build"]["steps"]
    return [step["run"] for step in steps if isinstance(step.get("run"), str)]


def test_worker_build_runs_dry_run() -> None:
    runs = _worker_build_runs()
    assert runs, "worker-build has no run: steps to pin"
    assert any("--dry-run" in block for block in runs), (
        "worker-build must pass --dry-run (verified ci.yml:693); "
        "without it the gate needs Cloudflare credentials"
    )


def test_worker_build_invokes_wrangler() -> None:
    runs = _worker_build_runs()
    assert runs, "worker-build has no run: steps to pin"
    assert any("wrangler deploy" in block for block in runs), (
        "worker-build must invoke wrangler deploy (verified ci.yml:693)"
    )


def test_worker_build_needs_no_secrets() -> None:
    text = CI_YML.read_text(encoding="utf-8")
    start = text.index("worker-build:")
    block = text[start : text.index("actionlint:", start)]
    assert "secrets." not in block, (
        "worker-build must stay credential-free; a secrets.* ref breaks fork PRs"
    )


def test_worker_build_matrix_matches_derived_workers() -> None:
    import json

    matrix = set(_ci()["jobs"]["worker-build"]["strategy"]["matrix"]["app"])
    assert matrix, "worker-build matrix.app is empty"
    derived = set()
    for manifest_path in sorted((REPO_ROOT / "apps").glob("*/package.json")):
        manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
        if (manifest_path.parent / "wrangler.toml").is_file() and (
            "wrangler" in manifest.get("devDependencies", {})
        ):
            derived.add(manifest_path.parent.name)
    assert derived, "derivation is empty; the comparison below would pass vacuously"
    assert matrix == derived, (
        f"matrix {sorted(matrix)} != derived {sorted(derived)}"
    )
