# Host CI runner

The script that posts the `local-ci` commit status for this repository, and the
`Every commit reaching main was reviewed` status for develop-to-main promotions.

It posts the same verdict twice: once as `local-ci`, with the repository token,
and once as `local-ci/app`, with the GitHub App's own installation token, so the
app row's creator is `digithings-ci[bot]`. With no app token there is no app
row at all: a row under another identity would be worse than no row.

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
| `review_applied.py` | decides `review-applied`: a review pass left findings and every thread is resolved or answered |
| `pr_template.py` | checks a PR body against the required sections and the Human Gate question |
  (`pr_template.py` is byte-identical; the runner and the review check carry the small

Tests are `tests/scripts/test_local_ci.py`, `test_review_applied.py` and
`test_pr_template.py`, so the repository's own `pytest` run covers the gate that
gates the repository.

## Running it

```
`--dry-run` prints the rendered plist and touches nothing: no write, no bootout, no
python3 scripts/local-ci/local_ci.py --pr 1234     # one PR
python3 scripts/local-ci/local_ci.py               # one tick over the queue
```

Two paths are environment-overridable so a dedicated clone can run the same code
without editing it: `LOCAL_CI_MAIN` (the checkout the checks run against) and
`LOCAL_CI_WT` (the scratch worktree root).

`install.sh` writes the launchd plist for a checkout and starts it:

```
`--dry-run` prints the rendered plist and touches nothing: no write, no bootout, no
scripts/local-ci/install.sh ~/Code/digithings
```

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
