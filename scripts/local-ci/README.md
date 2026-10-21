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
(`ai.digithings.local-ci`, `ai.digithings.twelvex-ci` and their post-merge
jobs) and the CI container (the Woodpecker worker). The runner asks
`launch_guard.py` before it does anything at all - before the lock, the
worktree, the log, GitHub - and the guard refuses anything else with exit 78
(`EX_CONFIG`) and a line in `~/.config/digithings/logs/local-ci/launch-guard.jsonl`.

The rule used to live only in the operating-rules skill, and on 21 Oct a seat ran
the runner twice from its own shell. The guard reads kernel and launchd facts
only: the pid of this process, the process tree, launchd's own table of the jobs
it runs, the pid launchd reports for the job, the canonical plist, the loaded
job's own arguments, and the container's entrypoint. It never reads `BASH_ENV`,
`PAPERCLIP_*` or `ZDOTDIR`, and it never calls `gh`, so unsetting those changes
nothing. It also never runs a tool from the `PATH`:
`launchctl` and `ps` are run from their absolute path and only when they are
root-owned files, so a seat that puts a fake `launchctl` first on the `PATH`
cannot answer the guard's own question with a job that reports the seat's pid.

What each launcher has to show:

- **the launchd daemon**: launchd's own job table (`launchctl list`) says a
  trusted label is running *this* pid; the parent pid is 1 and the process tree
  starts at launchd; the loaded job reports the same pid; the job was loaded
  from the canonical plist (`~/Library/LaunchAgents/<label>.plist`); the loaded
  job's arguments are exactly the arguments that plist names; and the script
  the job runs is either this file or a trusted driver script next to it
  (`postmerge_ci.py`, which drives `run_checks()` in-process for the post-merge
  check). The label in the environment (`XPC_SERVICE_NAME`) is recorded but never
  trusted - a seat can set it to anything. The pid tie is the fact a seat
  cannot forge cheaply: a seat can orphan its own process to launchd (`ppid`
  becomes 1) and claim the label - the first version of this guard allowed
  exactly that - but the job runs under its own pid, and a process that is not
  the job's process is refused.
- **the CI container**: the runner is under `/opt/local-ci`, its own parent is
  `worker_entrypoint.sh`, and the environment carries the CI credential. The
  container is the trust boundary: a seat that can `docker exec` into the
  worker already has the CI host and is out of scope.

The guard is asked at every entry point that does work - `main()`, the lock,
the worktree and the checks - not only in `main()`. The post-merge launchd job
runs `postmerge_ci.py`, which imports this runner and calls `run_checks()`
in-process without ever going through `main()`; a guard that only lived in
`main()` would not be asked on the path that job takes. The decision is
remembered for the process, so the extra asks cost nothing.

```
python3 scripts/local-ci/launch_guard.py --runner scripts/local-ci/local_ci.py
```

prints the decision and exits 0 (the run may proceed) or 78 (it is refused). It
is a diagnostic: it runs no check and posts nothing.

What the guard is not: a proof. At the same uid a seat can copy the runner and run
its own copy, drive the container with its own token, or write the canonical
plist itself and reload the job under a trusted label - the canonical plist is
user-writable, so its path proves where a job came from, not who wrote it.
What the guard does buy is that the cheap forgeries fail: an unset environment,
a forged label, an orphaned process tree, a job loaded from somewhere else, a
job that asks for one PR, a shadowed `launchctl`. The
queue-side provenance check (DIG-4794) is what makes a `local-ci` status count
only when it comes from the pipeline.

## Deploying it

The guard fails closed: a runner without `launch_guard.py` next to it refuses to
run at all (exit 78, before any side effect). So the two files have to land
together, and the order matters.

1. the guard lands in the repository (this change),
2. a trusted launcher is live - the launchd daemon has to be running under the
   label, or the container has to have the new runner in its image,
3. only then does the runner reach the host copy and the worker image.

The runner and the guard have to move together, in the same change, in every
place the runner lives:

- **the host copy** (`~/Code/local-ci/`): `local_ci.py` and `launch_guard.py`
  side by side. The host copy is its own checkout and has diverged from this
  repository, so it is synced deliberately, not copied over.
- **the worker image**: `Dockerfile.worker` copies `local_ci.py` into
  `/opt/local-ci`, and it has to copy `launch_guard.py` next to it, or the
  container's runner refuses every run. A guarded runner must never enter the
  image before the guard does.
- **the launchd job**: the plist `install.sh` writes points at the host copy,
  so the daemon picks up the guard with the runner.

The daemon that produces the pre-merge `local-ci` status and the post-merge
check is the one thing that must not go missing while the guard lands. If it
is frozen, the guard cannot be enabled on the host copy yet: the seat-shaped
hand-runs stop posting, and nothing else does either.

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
