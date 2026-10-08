"""Pin: the dependency freshness radar is weekly, clocked on the Worker, not on GitHub.

The DIG-1515 design note first shipped this job with ``on: schedule`` plus
``cron: '0 6 1 * *'`` inside the workflow. develop cannot carry that:
``tests/scripts/test_no_gha_schedules.py`` fails any workflow whose ``on``
contains ``schedule``, because every clock for this repo lives on the
digithings-cron Worker (``apps/digithings-cron``) and a GitHub cron on the
default branch would double-fire with it. ``secret-staleness`` is the precedent:
a ``workflow_dispatch``-only workflow whose clock is a ``wd()`` row plus a
``[triggers] crons`` entry in ``wrangler.toml``.

Same outcome the idea asked for -- a uv.lock-vs-PyPI comparison, posted as a
tracking issue -- on the one clock the repo actually owns. DIG-2277 moved the
cadence from monthly to weekly: security-pip-audit and security-npm-audit
already read the same lock every Monday, so monthly put new versions behind
known vulnerabilities rather than in front of them.
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

CRON = "23 6 * * MON"
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


def _steps() -> list[dict]:
    return _workflow()["jobs"]["dependency-freshness"]["steps"]


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


def test_the_clock_is_weekly() -> None:
    """DIG-2277 flipped this from monthly, and the pin exists so the flip cannot
    happen twice in either direction without a test failing.

    The original argument was that a weekly clock would bury the report. That was
    wrong about the cost: the publish step edits one standing issue in place, so
    weekly costs 52 edits of a single issue, not 52 issues. The real argument for
    weekly is the one below -- `security-pip-audit` (33 6 * * MON) already reads
    this same lock every Monday, so a monthly freshness clock would report new
    versions at a lower rate than we report known vulnerabilities in them.

    Read out of jobs.ts rather than asserted against the module literal, so this
    fails if the registered row's day-of-week ever changes.
    """
    row = re.search(
        rf'wd\(\s*"{re.escape(JOB_ID)}"\s*,\s*"([^"]+)"', JOBS_SOURCE.read_text(encoding="utf-8")
    )
    assert row, f'no wd("{JOB_ID}", "…") row in jobs.ts'
    registered = row.group(1)
    assert registered == CRON, f"jobs.ts registers {registered!r}, this suite pins {CRON!r}"
    assert registered.endswith("* * MON"), f"{registered!r} is not weekly on Mondays"


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
    Now that the radar is Monday-weekly it shares a day with ci-pr-hygiene
    (21 6 * * *), secret-staleness (17 6 1 * *) and both security audits
    (33/37 6 * * MON), so 06:23 has to stay clear of all of them."""
    block = WRANGLER.read_text(encoding="utf-8").split("[triggers]", 1)[1]
    crons = [
        line.split("#")[0].strip() for line in block.splitlines() if line.strip().startswith('"')
    ]
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


def test_a_failed_scan_cannot_blank_the_standing_report() -> None:
    """The one blocker a review found.

    The publish step edits the single open radar issue in place, so `if: always()`
    on it meant any upstream failure — and the fragile step behind it is a 2.4 GB
    `uv sync` plus 284 PyPI reads — published an empty table over a good report
    and reported success. The radar would have destroyed its own record
    once and had no way to explain why. It must fail loudly instead, and only
    ever edit a body it actually produced.
    """
    steps = _steps()
    publish = next(s for s in steps if s.get("name") == "Create/update tracking issue")
    assert "always()" not in str(publish.get("if", "")), (
        "the publish step must not run when a predecessor failed"
    )

    guards = [s for s in steps if "Guard" in str(s.get("name", ""))]
    assert guards, "an empty report has to be refused, not published over the good one"
    guard = guards[0]
    assert str(guard.get("if")) == "always()", (
        "the guard must also surface a failure that happened upstream of the scan"
    )
    assert "steps.report.outputs.table" in yaml.safe_dump(guard.get("env") or {}), (
        "read the table through env:, not ${{ }} interpolation into the script"
    )
    run = guard["run"]
    assert "-z" in run and "exit 1" in run, "the guard must actually fail the job"


def test_the_radar_creates_its_own_label_before_using_it() -> None:
    """`gh issue create --label` is fatal on a label that does not exist, and
    `radar` did not exist in this repo. Left alone, the first run would
    have died on a label lookup and reported nothing."""
    body = WORKFLOW.read_text(encoding="utf-8")
    assert body.index("gh label create radar") < body.index('--label "radar,')


def test_the_job_is_bounded_and_single_flighted() -> None:
    """An unbounded job is a stuck clock, and two overlapping dispatches would
    race each other on the same issue body — the radar edits one issue in
    place, so the loser of that race silently discards the winner's table."""
    job = _workflow()["jobs"]["dependency-freshness"]
    timeout = job.get("timeout-minutes", 0)
    assert 0 < timeout <= 30, f"timeout-minutes is {timeout!r}; 27 sibling workflows set one"

    concurrency = _workflow().get("concurrency") or {}
    assert concurrency.get("group"), "overlapping dispatches must share a concurrency group"
    assert concurrency.get("cancel-in-progress") is False, (
        "queue the second dispatch; cancelling the first would leave a half-run report"
    )
