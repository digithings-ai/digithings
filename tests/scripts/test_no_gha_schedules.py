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


_WORKFLOW_SUFFIXES = {".yml", ".yaml"}


def _on(doc: dict) -> object:
    if "on" in doc:
        return doc["on"]
    if True in doc:
        return doc[True]
    raise AssertionError("workflow missing on:")


def _has_schedule(on: object) -> bool:
    if isinstance(on, dict):
        return "schedule" in on
    if on == "schedule":
        return True
    return isinstance(on, list) and "schedule" in on


def schedule_offenders(workflow_dir: Path) -> list[str]:
    """Relative paths of workflow files that declare a ``schedule:`` trigger.

    A file that cannot be parsed is an offender. Skipping it would let a
    broken document hide a clock. The scan is recursive: a schedule under
    ``.github/workflows/<subdir>/`` is the same trigger GitHub would read.
    """
    offenders: list[str] = []
    paths = sorted(
        path
        for path in workflow_dir.rglob("*")
        if path.is_file() and path.suffix in _WORKFLOW_SUFFIXES
    )
    for path in paths:
        rel = path.relative_to(workflow_dir).as_posix()
        try:
            loaded = yaml.safe_load(path.read_text(encoding="utf-8"))
        except (yaml.YAMLError, UnicodeError):
            offenders.append(rel)
            continue
        if not isinstance(loaded, dict):
            offenders.append(rel)
            continue
        try:
            on = _on(loaded)
        except AssertionError:
            offenders.append(rel)
            continue
        if _has_schedule(on):
            offenders.append(rel)
    return offenders


def test_develop_workflows_have_no_gha_schedule() -> None:
    assert schedule_offenders(WORKFLOW_DIR) == []


def test_schedule_in_a_subfolder_is_an_offender(tmp_path: Path) -> None:
    nested = tmp_path / "nested" / "clock.yml"
    nested.parent.mkdir()
    nested.write_text("on:\n  schedule:\n    - cron: '0 9 * * 1'\n", encoding="utf-8")
    assert schedule_offenders(tmp_path) == ["nested/clock.yml"]


def test_yaml_extension_schedule_is_an_offender(tmp_path: Path) -> None:
    path = tmp_path / "clock.yaml"
    path.write_text("on: [workflow_dispatch, schedule]\n", encoding="utf-8")
    assert schedule_offenders(tmp_path) == ["clock.yaml"]


def test_unparseable_workflow_is_an_offender(tmp_path: Path) -> None:
    (tmp_path / "broken.yml").write_text("on: [\n  schedule: {", encoding="utf-8")
    (tmp_path / "later.yaml").write_text(
        "on:\n  schedule:\n    - cron: '0 0 * * 0'\n",
        encoding="utf-8",
    )
    assert schedule_offenders(tmp_path) == ["broken.yml", "later.yaml"]


def test_dispatch_only_workflow_is_clean(tmp_path: Path) -> None:
    (tmp_path / "manual.yml").write_text(
        "on:\n  workflow_dispatch: {}\njobs:\n  refresh:\n    steps:\n      - run: echo schedule\n",
        encoding="utf-8",
    )
    assert schedule_offenders(tmp_path) == []


def test_jobs_map_does_not_claim_a_digisearch_parity_clock() -> None:
    """digisearch_parity is not a workflow in this repo. Do not invent a cron."""
    text = JOBS_SOURCE.read_text(encoding="utf-8")
    # Both scrapes below name every builder in JOBS. A builder missing from this
    # alternation is invisible here, so the assertions below would pass against a
    # job they cannot see — a silent hole, not a green lane. wj = watch jobs
    # (DIG-3065), ow = OCC worker-native rows (DIG-3576). Add your builder in
    # the same edit that adds it to jobs.ts.
    ids = re.findall(r'(?:wd|rd|cj|pj|wj|ow)\(\s*"([^"]+)"', text)
    workflows = re.findall(r'(?:wd|rd|cj|pj|wj|ow)\([^)]*?"([^"]+\.yml)"', text, flags=re.DOTALL)
    assert "digisearch_parity" not in ids
    assert "digisearch-parity" not in ids
    assert "digisearch_parity.yml" not in workflows
    assert "digisearch-parity.yml" not in workflows
