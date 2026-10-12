"""Pin: the DataTap answer integrity check runs hourly, with no secret (#DIG-306).

The brief asked for ``on: schedule`` with ``cron: '17 * * * *'`` inside the
workflow. develop cannot carry that: ``tests/scripts/test_no_gha_schedules.py``
fails any workflow whose ``on`` contains ``schedule``, because every clock for
this repo lives on the digithings-cron Worker (``apps/digithings-cron``) and a
GitHub cron on develop would double-fire with it. ``secret-staleness`` is the
precedent: a ``workflow_dispatch``-only workflow whose clock is a ``wd()`` row
plus a ``[triggers] crons`` entry in ``wrangler.toml``.

Same outcome the brief wants — hourly at minute 17, zero credentials — on the
one clock the repo actually owns.
"""

from __future__ import annotations

import re
from pathlib import Path

import pytest
import yaml

pytestmark = pytest.mark.unit

REPO_ROOT = Path(__file__).resolve().parents[2]
WORKFLOW = REPO_ROOT / ".github" / "workflows" / "datatap-answer-check.yml"
JOBS_SOURCE = REPO_ROOT / "apps" / "digithings-cron" / "src" / "jobs.ts"
WRANGLER = REPO_ROOT / "apps" / "digithings-cron" / "wrangler.toml"

CRON = "17 * * * *"
JOB_ID = "datatap-answer-check"
MAKE_TARGET = "make datatap-answer-check"


MONOREPO_SLUG = "digithings-ai/digithings"


def _monorepo_const() -> str:
    """Name of the jobs.ts constant that holds the monorepo slug.

    Derived from the declaration instead of hardcoded. These pins are about the row
    targeting the monorepo, not about what the constant is called, so renaming the
    constant (DIG-2474) must not turn a repo-targeting pin into a build failure.
    Repointing the row elsewhere still fails: the name comes from the declaration
    that holds the slug, and the row must reference that exact name.
    """
    text = JOBS_SOURCE.read_text(encoding="utf-8")
    m = re.search(rf'const\s+(?P<name>\w+)\s*(?::[^=]+)?=\s*"{re.escape(MONOREPO_SLUG)}"', text)
    assert m, f"no jobs.ts constant declares {MONOREPO_SLUG}"
    return m.group("name")


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


def test_the_workflow_runs_the_check_through_the_make_target() -> None:
    """One source of truth: the same command the developer and the routine run."""
    body = WORKFLOW.read_text(encoding="utf-8")
    assert MAKE_TARGET in body


def test_the_workflow_does_not_swallow_the_exit_code() -> None:
    """Exit 1 and exit 2 must both surface. `continue-on-error` or `|| true`
    would turn a real fabrication signal, and a blind check, into green."""
    body = WORKFLOW.read_text(encoding="utf-8")
    assert "continue-on-error" not in body
    assert "|| true" not in body
    assert "|| exit 0" not in body


def test_the_workflow_introduces_no_secret_and_no_repo_variable() -> None:
    """The token comes out of DataTap's own public page. No credential is needed."""
    body = WORKFLOW.read_text(encoding="utf-8")
    assert "secrets." not in body
    assert "vars." not in body


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
    assert _monorepo_const() in args
    assert "datatap-answer-check.yml" in args
    assert "enabled: false" not in args, "the clock must actually be enabled"


def test_the_cron_is_in_the_wrangler_trigger() -> None:
    """Each enabled job.cron must appear in wrangler.toml [triggers] crons."""
    text = WRANGLER.read_text(encoding="utf-8")
    block = text.split("[triggers]", 1)[1]
    entry = next(line for line in block.splitlines() if line.strip().startswith(f'"{CRON}"'))
    assert f"# {JOB_ID}" in entry, "keep the job id as the trailing comment, like its neighbours"


def test_the_new_clock_does_not_collide_with_an_existing_one() -> None:
    """Off-grid minutes only; two enabled jobs on one minute share a runner."""
    block = WRANGLER.read_text(encoding="utf-8").split("[triggers]", 1)[1]
    crons = [line.split("#")[0].strip() for line in block.splitlines() if line.strip().startswith('"')]
    assert len(crons) == len(set(crons)), "two jobs on one cron will queue on a shared runner"