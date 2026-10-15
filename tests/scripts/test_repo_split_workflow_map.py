"""Pin the repo-split workflow map (DIG-3605, Chris 2026-10-14).

The approved list below is literal. The map module is the record. They must
name the same paths. A cron row must still be an enabled clock in jobs.ts.
A local-ci row must name an anchor that exists, or a DIG-3697 deploy script
that lands with that PR. A deletion row must have no enabled clock.

Measured against develop d227b6ed5 plus this branch.
"""

from __future__ import annotations

import importlib.util
import sys
from pathlib import Path

import pytest

pytestmark = pytest.mark.unit

REPO_ROOT = Path(__file__).resolve().parents[2]
JOBS_SOURCE = REPO_ROOT / "apps" / "digithings-cron" / "src" / "jobs.ts"
MAP_SOURCE = REPO_ROOT / "scripts" / "repo_split_workflow_map.py"
LEDGER = REPO_ROOT / "docs" / "ops" / "repo-split-workflow-map.md"

# Chris's list, plus the three R5 names the same comment gives
# (cron deploy, digichat image publish, gitleaks).
APPROVED: tuple[tuple[str, str], ...] = (
    ("R1", ".github/workflows/test-nautilus.yml"),
    ("R2", ".github/workflows/deploy-digiquant-runner.yml"),
    ("R2", ".github/workflows/pipeline-digiquant.yml"),
    ("R2", ".github/digiquant-pipeline.yml"),
    ("R2", ".github/workflows/pipeline-checkpoint-archive.yml"),
    ("R2", ".github/workflows/pipeline-market-data-refresh.yml"),
    ("R2", ".github/workflows/pipeline-research-metrics.yml"),
    ("R2", ".github/workflows/pipeline-digiquant-prices.yml"),
    ("R2", ".github/workflows/pipeline-digiquant-onchain.yml"),
    ("R2", ".github/workflows/pipeline-digiquant-tearsheets.yml"),
    ("R2", ".github/workflows/pipeline-digiquant-allocation-shadow.yml"),
    ("R2", ".github/workflows/sync-digiquant-runner-digikey-secret.yml"),
    ("R2", ".github/workflows/sync-digiquant-runner-mail-secrets.yml"),
    ("R2", ".github/workflows/test-digiquant.yml"),
    ("R3", ".github/workflows/deploy-digiquant-cloudflare.yml"),
    ("R3", ".github/workflows/test-dashboard.yml"),
    ("R4", ".github/workflows/book-pdf.yml"),
    ("R4", ".github/workflows/deploy-digithings-cloudflare.yml"),
    ("R4", ".github/workflows/refresh-repo-activity.yml"),
    ("R4", ".github/workflows/test-web.yml"),
    ("R6", ".github/workflows/datatap-answer-check.yml"),
    ("R6", ".github/workflows/occ-invite-key-rollout.yml"),
    ("R5", ".github/workflows/deploy-digithings-cron.yml"),
    ("R5", ".github/workflows/publish-digichat-image.yml"),
    ("R5", ".github/workflows/security-gitleaks.yml"),
)

LATER_ANCHORS = frozenset({"scripts/deploy/runner.sh", "scripts/deploy/cron.sh"})


def _load(name: str, path: Path):
    spec = importlib.util.spec_from_file_location(name, path)
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    # dataclass looks the class up in sys.modules while the class body runs.
    sys.modules[name] = module
    spec.loader.exec_module(module)
    return module


def _map():
    return _load("repo_split_workflow_map", MAP_SOURCE)


def _enabled_clocks() -> dict[str, set[str]]:
    """workflow filename -> enabled job ids, via the clock-pin parser."""
    pin = _load(
        "migrated_clocks",
        REPO_ROOT / "tests" / "scripts" / "test_migrated_workflows_still_clocked.py",
    )
    rows, _names, _targets = pin._job_rows()
    found: dict[str, set[str]] = {}
    for row in rows:
        if not row["enabled"]:
            continue
        found.setdefault(str(row["workflow"]), set()).add(str(row["id"]))
    return found


def test_the_map_is_exactly_the_approved_list():
    module = _map()
    assert {row.disposition for row in module.ROWS} <= set(module.DISPOSITIONS)
    recorded = {(row.repo, row.path) for row in module.ROWS}
    assert recorded == set(APPROVED)
    assert len(module.ROWS) == len(APPROVED)
    assert len(module.by_path()) == len(APPROVED)


def test_cron_rows_are_enabled_clocks():
    clocks = _enabled_clocks()
    for row in _map().ROWS:
        if row.disposition != "cloudflare-cron":
            continue
        assert row.clock_ids, row.path
        workflow = Path(row.path).name
        if row.path == ".github/digiquant-pipeline.yml":
            workflow = "pipeline-digiquant.yml"
            text = (REPO_ROOT / ".github/workflows" / workflow).read_text(encoding="utf-8")
            assert row.path in text
            assert (REPO_ROOT / row.path).is_file()
        else:
            assert (REPO_ROOT / row.path).is_file()
        have = clocks.get(workflow, set())
        missing = [job_id for job_id in row.clock_ids if job_id not in have]
        assert not missing, (row.path, missing)


def test_local_ci_rows_name_a_real_anchor_or_a_known_later_job():
    ci = (REPO_ROOT / ".github/workflows/ci.yml").read_text(encoding="utf-8")
    package = (REPO_ROOT / "apps/digithings-web/package.json").read_text(encoding="utf-8")
    for row in _map().ROWS:
        if row.disposition != "local-ci":
            continue
        assert (REPO_ROOT / row.path).is_file(), row.path
        if row.ci_uses:
            name = Path(row.path).name
            assert f"uses: ./.github/workflows/{name}" in ci
        if row.anchor_lands_later:
            assert row.anchor in LATER_ANCHORS
            assert not (REPO_ROOT / row.anchor).exists()
        elif row.anchor:
            assert (REPO_ROOT / row.anchor).is_file(), row.anchor
        if row.path.endswith("book-pdf.yml"):
            assert '"book:pdf"' in package
        if not row.armed:
            assert row.anchor == ""
            assert "API call" in row.note


def test_deletion_rows_have_no_enabled_clock():
    clocks = _enabled_clocks()
    names = []
    for path in (REPO_ROOT / ".github/workflows").glob("*.yml"):
        for line in path.read_text(encoding="utf-8").splitlines():
            if line.startswith("name:"):
                names.append(line.split(":", 1)[1].strip().strip('"'))
                break
    deletions = [row for row in _map().ROWS if row.disposition == "deletion"]
    assert len(deletions) == 1
    row = deletions[0]
    assert Path(row.path).name not in clocks
    assert (REPO_ROOT / row.path).is_file()
    assert row.anchor and (REPO_ROOT / row.anchor).is_file()
    assert "Pipeline: dashboard research" not in names


def test_the_ledger_names_every_mapped_path():
    text = LEDGER.read_text(encoding="utf-8")
    for row in _map().ROWS:
        assert row.path in text
        assert row.disposition in text


def test_this_change_does_not_call_cloudflare():
    text = MAP_SOURCE.read_text(encoding="utf-8")
    assert "api.cloudflare.com" not in text
    assert "wrangler deploy" not in text
    assert JOBS_SOURCE.is_file()
