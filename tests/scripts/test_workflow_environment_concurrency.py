"""A workflow gated on an `environment` approval must never sit in a queueing group (#2541).

`concurrency` without `cancel-in-progress` means *queue*: an arriving run waits for the
group's current occupant to finish. That is the right trade for a run that is doing work —
see CI_CONVENTIONS.md #7, which asks production pipelines for `cancel-in-progress: false`
precisely so a half-finished apply is never killed.

An `environment:` with required reviewers breaks the assumption underneath that rule. The job
occupies the group from the moment the run starts, including the whole time it sits in the
approval gate doing nothing, and `cancel-in-progress: false` protects *that* too. So one run
nobody approves does not delay the workflow, it stops the workflow — and it does so silently,
because every later run is evicted from the group's single pending slot by its successor and
so reports `cancelled` with zero jobs, which reads like a cancelled deploy rather than a
deploy that never happened. `db-migrate.yml` lost 15 days and migrations 066-070 that way.

This is asserted over **every** workflow rather than the one that broke, because the bug is a
property of the combination and nothing about it is specific to db-migrate: two other
workflows already declare a `production` environment, and the next one to do so would
reproduce it by copying an existing file. `docs-onboard-digithings.yml` was already correct
and is the reason its sibling run showed `waiting` while db-migrate showed `pending` during
the incident.

The escape is deliberately narrow — either supersede within the group, or use a group that
is unique per run so nothing ever queues. What is refused is the third shape: a shared group
that queues behind a run which may never be approved. See
``test_db_migrate_ledger_gate.py`` for why superseding is *safe* for db-migrate specifically
(a purely ledger-gated apply, so the newest run's work is a superset of what it displaces);
that argument has to be made per workflow and this test does not make it for you.
"""

from __future__ import annotations

from pathlib import Path

import pytest
import yaml

pytestmark = pytest.mark.unit

REPO_ROOT = Path(__file__).resolve().parents[2]
WORKFLOW_DIR = REPO_ROOT / ".github" / "workflows"

WORKFLOWS = sorted(p for p in WORKFLOW_DIR.glob("*.yml"))


def _gated_jobs(workflow: dict) -> dict[str, dict]:
    """Jobs guarded by an `environment:`, whatever form the key takes.

    `environment` accepts a bare string or a mapping with `name`/`url`, and both inherit the
    approval rules configured on that environment, so both count.
    """
    jobs = workflow.get("jobs") or {}
    return {
        name: job
        for name, job in jobs.items()
        if isinstance(job, dict) and job.get("environment") is not None
    }


def _concurrency(workflow: dict, job: dict) -> object | None:
    """The `concurrency` in force for this job — its own, else the workflow-wide one.

    A job-level group overrides rather than merges with the workflow-level one, so reading
    both would misreport a job that opts out of a bad workflow-wide default.
    """
    if "concurrency" in job:
        return job["concurrency"]
    return workflow.get("concurrency")


def test_at_least_one_workflow_is_environment_gated() -> None:
    """Guard the guard: an empty sweep would make every assertion below vacuous.

    The parametrised test only ever *skips* when no job is gated, so a rename of the
    `environment:` key — or a bug in `_gated_jobs` — would read as a green suite rather than
    as a lost invariant.
    """
    gated = {
        path.name: sorted(_gated_jobs(yaml.safe_load(path.read_text(encoding="utf-8")) or {}))
        for path in WORKFLOWS
    }
    assert any(gated.values()), (
        "no workflow job declares an `environment:`, which contradicts db-migrate.yml, "
        f"sync-architecture-vault.yml and docs-onboard-digithings.yml; found: {gated}"
    )


@pytest.mark.parametrize("path", WORKFLOWS, ids=lambda p: p.name)
def test_an_environment_gated_job_does_not_queue(path: Path) -> None:
    workflow = yaml.safe_load(path.read_text(encoding="utf-8")) or {}
    gated = _gated_jobs(workflow)
    if not gated:
        pytest.skip("no environment-gated job")

    for name, job in gated.items():
        where = f"{path.name}:{name}"
        concurrency = _concurrency(workflow, job)
        if concurrency is None:
            continue  # nothing to queue behind

        assert isinstance(concurrency, dict), (
            f"{where} is gated on environment {job['environment']!r} and uses the scalar form "
            f"`concurrency: {concurrency}`, which cannot carry cancel-in-progress. A run left "
            "unapproved then holds the group for as long as nobody approves it and every "
            "later run queues behind it forever (#2541)"
        )

        group = str(concurrency.get("group", ""))
        if "${{" in group:
            continue  # varies per run, so nothing queues in the first place

        assert concurrency.get("cancel-in-progress") is True, (
            f"{where} is gated on environment {job['environment']!r} and shares the static "
            f"concurrency group {group!r} without cancel-in-progress, so an unapproved run "
            "stops the workflow indefinitely instead of delaying it. Either supersede "
            "(cancel-in-progress: true, only if the newest run's work is a superset of what "
            "it displaces) or make the group unique per run (#2541)"
        )
