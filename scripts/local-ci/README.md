# Host CI runner

The script that posts the `local-ci` commit status for this repository, and the
`Every commit reaching main was reviewed` status for develop-to-main promotions.

It runs on the host (launchd), not in GitHub Actions. Since the free Actions
minutes are not a CI budget, this is the required check on `develop`: a PR that
this script has not passed does not merge.

## Why it lives here

It used to live only on one machine, in a directory with no git remote. That made
the gate that decides every merge unreviewable, unversioned, and one disk failure
away from taking the repository's ability to merge with it. It belongs in the repo
whose merges it gates, at the same version as the code it gates.

## Files

| file | what it does |
|---|---|
| `local_ci.py` | the tick: picks queued PRs, runs the static gates, posts the status |
| `launch_guard.py` | refuses a run that no trusted launcher started (DIG-4796) |
| `review_applied.py` | decides `review-applied`: a review pass left findings and every thread is resolved or answered |
| `pr_template.py` | checks a PR body against the required sections and the Human Gate question |
  (`pr_template.py` is byte-identical; the runner and the review check carry the small

Tests are `tests/scripts/test_local_ci.py`, `test_review_applied.py`,
`test_pr_template.py` and `test_launch_guard.py`, so the repository's own `pytest` run
covers the gate that gates the repository.

## Who may run it

Only two launchers may start this runner: the launchd daemon
(`ai.digithings.local-ci`) and the CI container (the Woodpecker worker). The runner
asks `launch_guard.py` before it does anything at all - before the lock, the
worktree, the log, GitHub - and the guard refuses anything else with exit 78
(`EX_CONFIG`) and a line in `~/.config/digithings/logs/local-ci/launch-guard.jsonl`.

The rule used to live only in the operating-rules skill, and on 21 Oct a seat ran
the runner twice from its own shell. The guard reads kernel and launchd facts
only: the parent process, the process tree, `XPC_SERVICE_NAME`, the loaded job's
own arguments, and the container's entrypoint. It never reads `BASH_ENV`,
`PAPERCLIP_*` or `ZDOTDIR`, and it never calls `gh`, so unsetting those changes
nothing.

```
python3 scripts/local-ci/launch_guard.py --runner scripts/local-ci/local_ci.py
```

prints the decision and exits 0 (the run may proceed) or 78 (it is refused). It
is a diagnostic: it runs no check and posts nothing.

What the guard is not: a proof. At the same uid a seat can copy the runner and run
its own copy, and the queue-side provenance check (DIG-4794) is what makes a
`local-ci` status count only when it comes from the pipeline.

## Running it

The runner does not run from a shell any more: `launch_guard.py` refuses a
hand-run with exit 78 before the first side effect, `--pr` and `--dry-run`
included. The two sanctioned ways to run it are the launchd daemon and the CI
container:

```
launchctl kickstart gui/501/ai.digithings.local-ci   # the daemon's own tick
```

The daemon tick picks the queued PRs itself, so a single PR does not need a
hand-run: it is picked up on the next tick.

Two paths are environment-overridable so a dedicated clone can run the same code
without editing it: `LOCAL_CI_MAIN` (the checkout the checks run against) and
`LOCAL_CI_WT` (the scratch worktree root).

`install.sh` writes the launchd plist for a checkout and starts it:

```
scripts/local-ci/install.sh ~/Code/digithings
```

`--dry-run` prints the rendered plist and touches nothing: no write, no bootout.

## Invariants this script is built around

- **A skip is never silence.** A memory or disk guard that forces a skip posts
  `failure` on the queued PRs, so merges block loudly instead of passing quietly.
- **Fork code never executes here.** Fork PRs get a `failure` naming the re-push
  path a maintainer must use.
- **Fails closed on a missing input.** If the review record or the PR body cannot
  be read, the check fails; it does not assume the best.
- **Static gates only.** Per-package pytest suites, compose validation, npm and
  pip audit, token canary, secret staleness, invite-key rollout and cron dispatch
  are not gated here (DIG-3605 owns the rest).

## Copyright and secrets

Nothing secret is printed, logged or committed. Logs live under
`~/.config/digithings/logs/local-ci/`; state and the tick lock under
`~/.config/digithings/state/`.

## Keeping the job loaded

This script installs the runner only. The job that keeps it loaded and breaks a wedged
tick is `dt-daemon-liveness`, published in the private `digiforge` repository at
`scripts/dt-daemon-liveness` (DIG-4478). Install that alongside, or a stopped runner looks
exactly like an idle one.
