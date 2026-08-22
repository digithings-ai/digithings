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
#   - `github.sha` identifies a commit, not a run. All three workflows in scope declare
#     `workflow_dispatch`, and two dispatches of the same unchanged ref share the SHA.
# `run_id` and `run_number` hold because no two *live* runs can share one, and a re-run
# reuses the id of the run it re-runs — so it cannot collide with anything but itself.
PER_RUN_TOKENS = ("github.run_id", "github.run_number")

# The gated jobs as they stand. Pinned rather than derived, so that removing an
# `environment:` cannot quietly turn an assertion into a skip — see the test below.
ENVIRONMENT_GATED = {
    "db-migrate.yml": {"migrate"},
    "docs-onboard-digithings.yml": {"apply"},
    "sync-architecture-vault.yml": {"sync"},
}


def _gated_jobs(workflow: dict) -> dict[str, dict]:
    """Jobs guarded by an `environment:`, whatever form the key takes.

    `environment` accepts a bare string or a mapping with `name`/`url`, and both inherit the
    approval rules configured on that environment, so both count.

    Blind spot worth knowing: this reads one file, so a caller's workflow-level group
    combined with a *callee's* `environment:` is invisible. Safe today on two counts —
    `ci.yml`'s group carries `cancel-in-progress: true`, and none of the 18 reusable
    workflows it calls is environment-gated — but adding an `environment:` to a
    `test-*.yml` would not be caught here.
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


def _cancel_is_an_expression(concurrency: dict) -> bool:
    """`cancel-in-progress` given as a `${{ }}` expression, which GitHub documents.

    Whether it supersedes is then not decidable from the file, so it cannot be relied on
    to end a starvation and is refused. It is refused *for that reason* — the message has
    to say so rather than report the key as absent, which is the same class of misleading
    verdict as rejecting the quoted `'true'` below.
    """
    value = concurrency.get("cancel-in-progress")
    return isinstance(value, str) and "${{" in value


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


def test_known_environment_gated_jobs_are_still_gated() -> None:
    """Guard the guard, per workflow rather than in aggregate.

    The parametrised test below only ever *skips* when a file has no gated job, so a lost
    `environment:` reads as green. An earlier version of this asserted merely that *some*
    workflow was gated, which was not enough: dropping `environment: production` from
    db-migrate.yml's `migrate` job and restoring `cancel-in-progress: false` reproduces
    #2541 verbatim on the one workflow this file was written for, and `any(...)` stayed
    satisfied by its two siblings — `3 passed, 61 skipped`, exit 0.

    So the known gated jobs are pinned. New ones need no edit here; removing one has to be
    a deliberate change to this list, which is the point.
    """
    gated = {
        path.name: set(_gated_jobs(yaml.safe_load(path.read_text(encoding="utf-8")) or {}))
        for path in WORKFLOWS
    }
    lost = {
        name: sorted(jobs - gated.get(name, set()))
        for name, jobs in ENVIRONMENT_GATED.items()
        if not jobs <= gated.get(name, set())
    }
    assert not lost, (
        f"these jobs no longer declare an `environment:`, so the sweep below now skips them "
        f"instead of asserting anything: {lost}. Either the gate was removed — in which case "
        "#2541 can recur there unnoticed — or `_gated_jobs` stopped recognising the key"
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

            assert not _cancel_is_an_expression(concurrency), (
                f"{where} is gated on environment {job['environment']!r}, shares the static "
                f"concurrency group {group!r}, and decides cancel-in-progress with the "
                f"expression {concurrency['cancel-in-progress']!r}. Whether it supersedes is "
                "not decidable from this file, so it cannot be relied on to end a starvation "
                "(#2541)"
            )

            assert _cancels_in_progress(concurrency), (
                f"{where} is gated on environment {job['environment']!r} and shares the static "
                f"concurrency group {group!r} without cancel-in-progress, so an unapproved run "
                "stops the workflow indefinitely instead of delaying it. Either supersede "
                "(cancel-in-progress: true, only if the newest run's work is a superset of what "
                "it displaces) or make the group unique per run (#2541)"
            )
