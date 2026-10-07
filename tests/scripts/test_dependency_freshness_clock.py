"""Pin: the dependency freshness radar is monthly, clocked on the Worker, not on GitHub.

The DIG-1515 design note first shipped this job with ``on: schedule`` plus
``cron: '0 6 1 * *'`` inside the workflow. develop cannot carry that:
``tests/scripts/test_no_gha_schedules.py`` fails any workflow whose ``on``
contains ``schedule``, because every clock for this repo lives on the
digithings-cron Worker (``apps/digithings-cron``) and a GitHub cron on the
default branch would double-fire with it. ``secret-staleness`` is the precedent:
a ``workflow_dispatch``-only workflow whose clock is a ``wd()`` row plus a
``[triggers] crons`` entry in ``wrangler.toml``.

Same outcome the idea asked for -- a monthly uv.lock-vs-PyPI comparison, posted
as a tracking issue -- on the one clock the repo actually owns.
"""

from __future__ import annotations

import re
from pathlib import Path

import pytest
import yaml

pytestmark = pytest.mark.unit

REPO_ROOT = Path(__file__).resolve().parents[2]
WORKFLOW = REPO_ROOT / ".github" / "workflows" / "pipeline-dependency-freshness.yml"
JOBS_SOURCE = REPO_ROOT / "apps" / "digithings-cron" / "src" / "jobs.ts"
JOBS_TEST = REPO_ROOT / "apps" / "digithings-cron" / "src" / "jobs.test.ts"
WRANGLER = REPO_ROOT / "apps" / "digithings-cron" / "wrangler.toml"
SCRIPT = REPO_ROOT / "scripts" / "dependency_freshness.py"

CRON = "23 6 1 * *"
JOB_ID = "dependency-freshness"


def _workflow() -> dict:
    assert WORKFLOW.exists(), f"{WORKFLOW.relative_to(REPO_ROOT)} is the second line of defence"
    return yaml.safe_load(WORKFLOW.read_text(encoding="utf-8"))


def _on(doc: dict) -> object:
    if "on" in doc:
        return doc["on"]
    if True in doc:  # YAML 1.1 parses a bare `on:` key as the boolean True
        return doc[True]
    raise AssertionError("workflow missing on:")


def test_the_clock_workflow_exists() -> None:
    _workflow()


def test_the_workflow_has_no_github_schedule_because_develop_forbids_one() -> None:
    """develop carries no on.schedule. The clock is the Worker's wd() row."""
    on = _on(_workflow())
    rendered = yaml.safe_dump(on)
    assert "schedule" not in rendered


def test_the_workflow_is_workflow_dispatch_only() -> None:
    on = _on(_workflow())
    rendered = yaml.safe_dump(on)
    assert "workflow_dispatch" in rendered


def test_the_clock_is_monthly() -> None:
    """The finding was that nobody sees a major arriving. A weekly clock would
    bury the report; monthly is the cadence the idea asked for."""
    assert CRON.endswith("1 * *"), f"{CRON!r} is not monthly on the 1st"


def test_the_clock_is_registered_on_the_cron_worker() -> None:
    text = JOBS_SOURCE.read_text(encoding="utf-8")
    assert re.search(
        rf'wd\(\s*"{re.escape(JOB_ID)}"\s*,\s*"{re.escape(CRON)}"',
        text,
    ), f'no wd("{JOB_ID}", "{CRON}", …) row in jobs.ts'


def test_the_clock_row_targets_this_workflow_on_develop() -> None:
    text = JOBS_SOURCE.read_text(encoding="utf-8")
    row = re.search(rf'wd\(\s*"{re.escape(JOB_ID)}"(?P<args>[^)]*)\)', text, flags=re.DOTALL)
    assert row, f"no wd() row for {JOB_ID}"
    args = row.group("args")
    assert "DIGITHINGS" in args
    assert "pipeline-dependency-freshness.yml" in args
    assert "enabled: false" not in args, "the clock must actually be enabled"


def test_the_cron_is_in_the_wrangler_trigger() -> None:
    """Each enabled job.cron must appear in wrangler.toml [triggers] crons."""
    text = WRANGLER.read_text(encoding="utf-8")
    block = text.split("[triggers]", 1)[1]
    entry = next(line for line in block.splitlines() if line.strip().startswith(f'"{CRON}"'))
    assert f"# {JOB_ID}" in entry, "keep the job id as the trailing comment, like its neighbours"


def test_the_pinned_cron_set_is_updated() -> None:
    """jobs.test.ts asserts uniqueEnabledCrons() by exact ordered equality, and
    the enabled id list by exact set equality."""
    text = JOBS_TEST.read_text(encoding="utf-8")
    assert f'"{CRON}"' in text, "ENABLED_CRONS must gain the new clock at its JOBS position"
    assert f'"{JOB_ID}"' in text, "PATH_A_ENABLED_IDS must gain the new job id"


def test_the_new_clock_does_not_collide_with_an_existing_one() -> None:
    """Off-grid minutes only; two enabled jobs on one minute share a runner.
    secret-staleness already holds 17 6 1 *, so this must not sit on :17."""
    block = WRANGLER.read_text(encoding="utf-8").split("[triggers]", 1)[1]
    crons = [line.split("#")[0].strip() for line in block.splitlines() if line.strip().startswith('"')]
    assert len(crons) == len(set(crons)), "two jobs on one cron will queue on a shared runner"


def test_the_workflow_runs_the_shared_script_not_an_inline_copy() -> None:
    """One source of truth, so a test can cover the parsing the radar depends on."""
    body = WORKFLOW.read_text(encoding="utf-8")
    assert "scripts/dependency_freshness.py" in body
    assert SCRIPT.exists(), "the script the workflow calls must be committed, not implied"


def test_the_workflow_writes_step_outputs_to_github_output() -> None:
    """Printing the report to stdout leaves steps.report.outputs.* empty, and the
    issue body then ships blank. This was one of the three defects DIG-1515 shipped
    with and had to fix before its first run."""
    body = WORKFLOW.read_text(encoding="utf-8")
    assert '>> "$GITHUB_OUTPUT"' in body


def test_the_workflow_changes_no_bound() -> None:
    """The idea was visibility, not a constraint change. A `uv lock --upgrade` or a
    rewritten pyproject bound inside this workflow would turn a radar into an
    unattended upgrade."""
    body = WORKFLOW.read_text(encoding="utf-8")
    assert "--upgrade" not in body
    assert "uv add" not in body
    assert "uv lock" not in body.replace("uv.lock", "").replace("uv lock file", "")