"""A workflow gated on an `environment` approval must never sit in a queueing group (#2541).

`concurrency` without `cancel-in-progress` means *queue*: an arriving run waits for the
group's current occupant to finish. That is the right trade for a run that is doing work —
see `docs/agents/CI_CONVENTIONS.md` #7, which asks production pipelines for
`cancel-in-progress: false`
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

The other half of the hazard is that the environment changes *after* this file was written,
in the GitHub UI, where no test runs. A job gated on `cron` (added 2026-10-04 for DIG-248) is
invisible to this sweep the moment someone arms a required reviewer on `cron`: 32 pipelines
would then stop silently, exactly as db-migrate did, with every assertion here still green.
`.github/environments.json` records the protection rules of every environment, this module
reads it to decide which gated jobs may queue (an environment that cannot wait never leaves
the approval gate, so the queue it would create is not one), and
`scripts/secret_staleness_check.py` re-reads the live API so the manifest cannot quietly
become a lie. An environment missing from the manifest is a test failure, not a skip.

The escape is deliberately narrow — either supersede within the group, or use a group that
is unique per run so nothing ever queues. What is refused is the third shape: a shared group
that queues behind a run which may never be approved. Superseding was *safe* for db-migrate
specifically (a purely ledger-gated apply, so the newest run's work was a superset of what it
displaced), which `test_db_migrate_ledger_gate.py` used to argue and which the 2026-10-01
strict-essentials cut (`f54af7052`) deleted along with the workflow. That argument has to be
made per workflow and this test does not make it for you.
"""

from __future__ import annotations

from pathlib import Path

import pytest
import yaml

from scripts.secret_staleness_check import can_wait, manifest_environments

pytestmark = pytest.mark.unit

REPO_ROOT = Path(__file__).resolve().parents[2]
WORKFLOW_DIR = REPO_ROOT / ".github" / "workflows"
MANIFEST_PATH = REPO_ROOT / ".github" / "environments.json"

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
# 2026-10-01 GHA strict-essentials: former gated workflows (db-migrate,
# docs-onboard-digithings, sync-architecture-vault) deleted from tree. New
# environment-gated jobs still get caught by the parametrised sweep below;
# pin any survivors here so dropping `environment:` cannot quietly skip.
#
# 2026-10-04 (DIG-330): this was committed **empty**, so
# `test_known_environment_gated_jobs_are_still_gated` iterated an empty dict, `lost` was
# always empty, and the assert could not fire. Deleting `environment: cron` from
# `pipeline-digiquant.yml` left the whole `tests/scripts` suite green. The pin is the only
# thing that makes a *lost* gate visible — the sweep only asserts about gates that are
# still there — so it is now populated, and `test_the_pin_is_not_empty` fails if it is ever
# emptied again.
ENVIRONMENT_GATED: dict[str, set[str]] = {
    # `cron` — 32 jobs declared gated on 2026-10-04 for DIG-248, on the 18 files that read a
    # non-automatic `secrets.*` name. The gate is what makes an environment-scoped value
    # readable by a job at all, so once the values move out of repo and org scope, one of
    # these jobs losing its `environment:` line resolves that name to empty while every
    # check here still passes. Until that move lands the gate is inert — the `cron`
    # environment holds 0 secrets and every name still resolves at repo or org scope — so
    # this is a precondition for DIG-248 rather than a live break today.
    "agent-backlog-snapshot.yml": {"snapshot"},
    "agent-pr-finalizer.yml": {"finalize"},
    "deploy-digithings-cron.yml": {"deploy"},
    "execution-cron-check.yml": {"probe"},
    "pipeline-checkpoint-archive.yml": {"archive"},
    "pipeline-continuous-improvement.yml": {"digest"},
    "pipeline-digiquant-onchain.yml": {"bitview-ingest"},
    "pipeline-digiquant-prices.yml": {"fx-refresh", "fx-candles", "at-open", "eod-macro"},
    "pipeline-digiquant-tearsheets.yml": {"tearsheets"},
    "pipeline-digiquant.yml": {"run"},
    "pipeline-maintenance.yml": {
        "dependency-audit",
        "stale-branches",
        "doc-links",
        "adr-numbering",
        "agents-drift",
        "architecture-drift",
        "stale-issues",
        "stale-prs",
        "label-coverage",
        "workflow-health",
        "duplicate-issues",
        "project-fields-backfill",
    },
    "pipeline-market-data-refresh.yml": {"refresh"},
    "pipeline-provider-review.yml": {"review"},
    "pipeline-research-metrics.yml": {"refresh"},
    "project-enforce-assignment.yml": {"orphan-check"},
    "sync-digiquant-runner-digikey-secret.yml": {"sync-runner-house"},
    "sync-digiquant-runner-mail-secrets.yml": {"sync-runner-mail"},
    "token-canary.yml": {"canary"},
    # `production` — the one job whose environment *can* make a run wait, and therefore
    # the one the queueing assertions actually bite on. Its reviewer gate is intentional
    # and its concurrency group has to keep superseding.
    "deploy-digiquant-runner.yml": {"deploy"},
}


def _manifest() -> dict[str, dict]:
    """Protection rules per environment, as committed in `.github/environments.json`.

    Read as data rather than derived from the workflows, because the whole point is that
    the two can disagree: the workflows say *which* environment a job is gated on, the
    manifest says *whether that environment can make a run wait*, and that second fact
    lives only in the GitHub UI. `can_wait` is imported from the script that re-checks
    the manifest against the live API, so a test and the monthly report cannot end up
    disagreeing about what counts as safe.
    """
    environments = manifest_environments(MANIFEST_PATH)
    assert environments, (
        f"{MANIFEST_PATH.relative_to(REPO_ROOT)} has no `environments` map. The sweep below "
        "decides whether a gated job may queue from that map, so an unreadable manifest "
        "has to be a failure rather than a silently empty one"
    )
    return environments


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


def test_the_pin_is_not_empty() -> None:
    """The pin is load-bearing, so an empty one is a failure rather than a vacuous pass.

    `test_known_environment_gated_jobs_are_still_gated` is the only thing that can see a
    *lost* `environment:` — the sweep below only ever asserts about gates that are still
    there, and skips the rest. An empty `ENVIRONMENT_GATED` therefore does not make it
    stricter, it makes it incapable of failing at all.

    That is not hypothetical: DIG-330 found this file's pin committed as `{}` on 2026-10-04,
    with the comment above it claiming the gated jobs were pinned. Deleting
    `environment: cron` from `pipeline-digiquant.yml` then left the entire `tests/scripts`
    suite green. The 33 jobs that read environment-scoped secrets after DIG-248 are now
    listed explicitly, and this asserts the list has not been emptied again.

    Two limits worth knowing, both deliberate. This catches *total* emptying, not a single
    dropped entry — there is no reverse check that the pin covers every gate in the tree,
    because requiring one would contradict the design above ("new ones need no edit here")
    and a new gate is already caught by the sweep. And a renamed or deleted workflow reports
    here as a lost gate even though no `environment:` was removed;
    `test_the_pin_is_not_empty` names that case accurately.
    """
    assert ENVIRONMENT_GATED, (
        "ENVIRONMENT_GATED is empty, so test_known_environment_gated_jobs_are_still_gated "
        "cannot fail and a removed `environment:` is invisible. Repopulate it from "
        "`_gated_jobs` over .github/workflows — do not delete the entries."
    )
    missing = sorted(name for name in ENVIRONMENT_GATED if not (WORKFLOW_DIR / name).exists())
    assert not missing, (
        f"pinned workflow file(s) do not exist, so every job pinned under them reads as a "
        f"lost gate: {missing}. A workflow that no longer exists is a rename or a deletion, "
        f"not a removed `environment:` — move its entries to the new filename, or drop them "
        f"if the workflow is gone."
    )


@pytest.mark.parametrize("path", WORKFLOWS, ids=lambda p: p.name)
def test_an_environment_gated_job_does_not_queue(path: Path) -> None:
    workflow = yaml.safe_load(path.read_text(encoding="utf-8")) or {}
    gated = _gated_jobs(workflow)
    if not gated:
        pytest.skip("no environment-gated job")

    manifest = _manifest()

    for name, job in gated.items():
        environment = (
            job["environment"]["name"]
            if isinstance(job["environment"], dict)
            else job["environment"]
        )
        assert environment in manifest, (
            f"{path.name}:{name} is gated on environment {environment!r}, which is not in "
            f"{MANIFEST_PATH.relative_to(REPO_ROOT)}. The queueing rules below cannot be "
            "checked without knowing whether that environment can make a run wait, so this "
            "is a failure rather than a skip — add it to the manifest with its protection "
            "rules from the environments API"
        )
        if not can_wait(manifest[environment]):
            # The job starts immediately, so a shared group cannot be held by an
            # unapproved run and the invariant cannot be violated here. The manifest
            # saying otherwise (or wrongly) is caught by the two tests above.
            continue

        for scope, concurrency in _concurrency_scopes(workflow, job):
            where = f"{path.name}:{name} ({scope})"

            assert isinstance(concurrency, dict), (
                f"{where} is gated on environment {environment!r} and uses the scalar "
                f"form `concurrency: {concurrency}`, which cannot carry cancel-in-progress. A "
                "run left unapproved then holds the group for as long as nobody approves it "
                "and every later run queues behind it forever (#2541)"
            )

            group = str(concurrency.get("group", ""))
            if any(token in group for token in PER_RUN_TOKENS):
                continue  # genuinely distinct per run, so nothing ever queues behind it

            assert not _cancel_is_an_expression(concurrency), (
                f"{where} is gated on environment {environment!r}, shares the static "
                f"concurrency group {group!r}, and decides cancel-in-progress with the "
                f"expression {concurrency['cancel-in-progress']!r}. Whether it supersedes is "
                "not decidable from this file, so it cannot be relied on to end a starvation "
                "(#2541)"
            )

            assert _cancels_in_progress(concurrency), (
                f"{where} is gated on environment {environment!r} and shares the static "
                f"concurrency group {group!r} without cancel-in-progress, so an unapproved run "
                "stops the workflow indefinitely instead of delaying it. Either supersede "
                "(cancel-in-progress: true, only if the newest run's work is a superset of what "
                "it displaces) or make the group unique per run (#2541)"
            )


def test_every_declared_environment_is_in_the_manifest() -> None:
    """Fail closed on an environment whose protection rules are unknown here.

    Without this, adding `environment: something-new` would make the sweep skip the job
    while looking green — the same hole `test_known_environment_gated_jobs_are_still_gated`
    was written to close from the other direction.
    """
    manifest = _manifest()
    unknown: dict[str, set[str]] = {}
    for path in WORKFLOWS:
        workflow = yaml.safe_load(path.read_text(encoding="utf-8")) or {}
        for name, job in _gated_jobs(workflow).items():
            environment = (
                job["environment"]["name"]
                if isinstance(job["environment"], dict)
                else job["environment"]
            )
            if environment not in manifest:
                unknown.setdefault(str(environment), set()).add(f"{path.name}:{name}")
    assert not unknown, (
        f"workflows gate on environment(s) missing from "
        f"{MANIFEST_PATH.relative_to(REPO_ROOT)}: {unknown}"
    )


def test_the_cron_environment_cannot_wait() -> None:
    """The property DIG-248 depends on, pinned here so the manifest cannot excuse itself.

    32 jobs across 18 workflows were declared `environment: cron` so that the CI-read
    secret names can be moved out of repo and org scope — GitHub only exposes an
    environment-scope secret to a job that declares that environment. That plan is
    worthless if `cron` ever gains a required reviewer: the jobs would then be correct on
    paper and every scheduled pipeline would stall like #2541. The live check lives in
    `scripts/secret_staleness_check.py`; this pins the intent at review time.
    """
    rules = _manifest().get("cron")
    assert rules is not None, f"`cron` is missing from {MANIFEST_PATH.relative_to(REPO_ROOT)}"
    assert rules.get("required_reviewers") == [], (
        "an environment-scoped cron gate must not require review: 32 jobs would sit in the "
        "approval gate and stop their workflows, the #2541 failure mode"
    )
    assert int(rules.get("wait_timer_minutes") or 0) == 0, (
        "an environment-scoped cron gate must not add a wait timer, for the same reason"
    )
    assert rules.get("deployment_branches") is None, (
        "`cron` is dispatched from the digithings-cron Worker on many refs; a branch policy "
        "would skip the job rather than run it"
    )
