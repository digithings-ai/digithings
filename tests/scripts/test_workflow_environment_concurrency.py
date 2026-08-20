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

# Both suffixes: GitHub reads either, so a `.yaml` workflow is not exempt from the
# invariant just because the repo happens to spell most of them `.yml`.
WORKFLOWS = sorted(p for p in WORKFLOW_DIR.iterdir() if p.suffix in {".yml", ".yaml"})

# A `${{ }}` in a concurrency group does NOT imply the group varies per run. `github.ref`
# is the constant `refs/heads/main` for every push to main, and
# `github.event.pull_request.number` is constant for the life of a PR — both queue exactly
# like a literal. Only the run's own identity is genuinely distinct every time.
#
# Two near-misses are deliberately *not* in this list, because each is a shared group
# wearing a `${{ }}`:
#   - `github.run_attempt` is `1` for every first-attempt run, so `x-${{ github.run_attempt }}`
#     is the single literal group `x-1` for essentially every run there has ever been.
#   - `github.sha` identifies a commit, not a run. Both workflows in scope declare
#     `workflow_dispatch`, and two dispatches of the same unchanged ref share the SHA.
# A `waiting` run cannot be re-run, so a re-run can never collide with the occupant that
# starved it — which is why run_id and run_number hold even under re-run.
PER_RUN_TOKENS = ("github.run_id", "github.run_number")


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


def _concurrency_scopes(workflow: dict, job: dict) -> list[tuple[str, object]]:
    """Every `concurrency` block that can make this job queue, labelled by scope.

    Both scopes are returned, not just the narrowest. #2541 is its own counterexample to
    reading only one: the group that starved migrations 066-070 was `db-migrate.yml`'s
    **workflow-level** `concurrency: db-migrate`, while the `environment: production` sat on
    the `migrate` job. A job-level group overrides the workflow-level one *for the job*, but
    the run still occupies the workflow-level group for the whole time it sits in the
    approval gate — so treating a job-level block as a replacement would let three benign
    lines hide the exact defect this file exists to catch.
    """
    scopes: list[tuple[str, object]] = []
    if workflow.get("concurrency") is not None:
        scopes.append(("workflow-level", workflow["concurrency"]))
    if job.get("concurrency") is not None:
        scopes.append(("job-level", job["concurrency"]))
    return scopes


def _cancels_in_progress(concurrency: dict) -> bool:
    """Whether this block supersedes rather than queues.

    GitHub accepts `cancel-in-progress: 'true'` as well as the bare boolean, and YAML hands
    back a string for the quoted form. Rejecting it would be a false positive on a workflow
    that is in fact safe.
    """
    value = concurrency.get("cancel-in-progress")
    if isinstance(value, str):
        return value.strip().lower() == "true"
    return value is True


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
        for scope, concurrency in _concurrency_scopes(workflow, job):
            where = f"{path.name}:{name} ({scope})"

            assert isinstance(concurrency, dict), (
                f"{where} is gated on environment {job['environment']!r} and uses the scalar "
                f"form `concurrency: {concurrency}`, which cannot carry cancel-in-progress. A "
                "run left unapproved then holds the group for as long as nobody approves it "
                "and every later run queues behind it forever (#2541)"
            )

            group = str(concurrency.get("group", ""))
            if any(token in group for token in PER_RUN_TOKENS):
                continue  # genuinely distinct per run, so nothing ever queues behind it

            assert _cancels_in_progress(concurrency), (
                f"{where} is gated on environment {job['environment']!r} and shares the static "
                f"concurrency group {group!r} without cancel-in-progress, so an unapproved run "
                "stops the workflow indefinitely instead of delaying it. Either supersede "
                "(cancel-in-progress: true, only if the newest run's work is a superset of what "
                "it displaces) or make the group unique per run (#2541)"
            )
