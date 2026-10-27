# Host CI runner

The script that posts the `local-ci` commit status for this repository. It also
judges develop-to-main promotions with the repository's own review-coverage
logic, but it publishes no row for main's required review context: that context
has one producer, the `ci-review-coverage.yml` workflow (DIG-4507).

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
| `launch_guard.py` | refuses a run that no trusted launcher started (DIG-4796) |
| `import_preflight.py` | refuses a tick when a module the runner imports is missing from the install (DIG-5585) |
| `check_required_context_producers.py` | asserts every required context has exactly one producer (DIG-4507) |
| `review_applied.py` | decides `review-applied`: a review pass left findings and every thread is resolved or answered |
| `pr_template.py` | checks a PR body against the required sections and the Human Gate question |
  (`pr_template.py` is byte-identical; the runner and the review check carry the small

Tests are `tests/scripts/test_local_ci.py`, `test_review_applied.py`,
`test_pr_template.py`, `test_launch_guard.py`,
`test_check_required_context_producers.py` and `test_import_preflight.py`, so
the repository's own `pytest` run covers the gate that gates the repository.

## The review context has one producer (DIG-4507)

Main requires `Every commit reaching main was reviewed`, pinned to the Actions
app. That verdict is produced by `.github/workflows/ci-review-coverage.yml`,
whose job name is the context name and whose check run carries the app.

The runner still walks the promotion range with the same
`scripts/check_review_coverage.py`, and keeps `pr<N>-review-<sha>.log` as
evidence, but it posts nothing under that name. Two implementations of one
required context disagree, and a commit status posted with a user token carries
no app id, so it could never satisfy the pin anyway. The judgement log's mtime
is what the hourly re-check keys on.

`check_required_context_producers.py` guards the invariant: for every required
context it can read from main's protection it counts the producers (workflow
job names and host python sources) and requires exactly one, and for an
app-pinned context it requires the survivor to be the workflow. The runner runs
it once per tick and logs the result; a violation is loud in the log and never
fatal to the tick. An unreadable protection is reported, not failed.

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
  `worker_entrypoint.sh` (the path has to be one of that parent's own
  arguments, not a mention of it somewhere in a command line), and the
  environment carries the CI credential. The container is the trust boundary: a
  seat that can `docker exec` into the worker already has the CI host and is
  out of scope.

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
its own copy, drive the container with its own token, write the canonical
plist itself and reload the job under a trusted label - the canonical plist is
user-writable, so its path proves where a job came from, not who wrote it - or
replace the runner, the driver and the guard in the checkout they live in.
That last one needs no cleverness: the guard is only ever asked by the file it
guards, so a check that lives inside the files it protects does not survive
their replacement. What the guard does buy is that the cheap forgeries fail: an
unset environment, a forged label, an orphaned process tree, a job loaded from
somewhere else, a job that asks for one PR, a shadowed `launchctl`. The
queue-side provenance check (DIG-4794) is what makes a `local-ci` status count
only when it comes from the pipeline.

## When the install is incomplete

A trusted launcher is not enough: the checkout also has to be complete. The
runner imports its helpers with a `None` fallback and each helper fails closed.
That is the right answer to one missing fact and the wrong answer to a broken
install. On 24 Oct 2026 a checkout without `scripts/review_pass_filter.py` left
eight PRs red on `review-applied` with "no review pass left comments": the
status blamed the review while the missing file was the fault (DIG-4674).

`import_preflight.py` resolves, before anything else happens, every module the
runner imports - transitively, including the shared modules one directory up
(`scripts/review_pass_filter.py`) and the modules the runner loads by file path
(`check_required_context_producers.py`) - and refuses the tick when one is
absent. The refusal exits 78 (`EX_CONFIG`) with a log line that names the
missing module and the module that imports it, so a broken install reads as a
broken install. No lock is taken, no worktree is built and no status is posted.

Check an install without ticking it:

```
python3 scripts/local-ci/import_preflight.py scripts/local-ci/local_ci.py
```

`install.sh` asks the same question before it renders the plist or touches the
job: it requires `import_preflight.py` next to the runner, then runs it against
the checkout's `local_ci.py` under `/usr/bin/python3`, the interpreter the plist
names. A checkout with a module missing is refused, with the module named, so an
installer cannot point the daemon at a tree that would refuse every tick
(DIG-5725).

## Deploying it

The guard fails closed: a runner without `launch_guard.py` next to it refuses to
run at all (exit 78, before any side effect). The install check fails closed the
same way, so the runner and every module it imports have to land together. The
order matters. `install.sh` refuses a checkout that carries the runner but not
the guard, and a checkout where any module the runner imports does not resolve,
for the same reason: an installer must not be able to point the daemon at a
pre-guard or incomplete checkout and reopen the hole (DIG-4796, DIG-5725).

1. the guard lands in the repository (this change),
2. a trusted launcher is live - the launchd daemon has to be running under the
   label, or the container has to have the new runner in its image,
3. only then does the runner reach the host copy and the worker image.

The runner and the guard have to move together, in the same change, in every
place the runner lives:

- **the host copy** (`~/Code/local-ci/`): `local_ci.py` and `launch_guard.py`
  side by side, plus the modules the runner imports (`review_applied.py`,
  `pr_template.py`, `import_preflight.py`,
  `check_required_context_producers.py`) and the shared
  `scripts/review_pass_filter.py` one directory up. The host copy is its own
  checkout and has diverged from this repository, so it is synced deliberately,
  not copied over.
- **the worker image**: `Dockerfile.worker` copies `local_ci.py` into
  `/opt/local-ci`, and it has to copy `launch_guard.py` next to it, or the
  container's runner refuses every run. It also has to copy the modules the
  runner imports - `review_applied.py`, `pr_template.py`,
  `import_preflight.py`, `check_required_context_producers.py` and
  `review_pass_filter.py` (next to the runner in the container's flat layout) -
  or the install check refuses every run for the same reason. A guarded runner
  must never enter the image before the guard does.
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
scripts/local-ci/install.sh --self-update ~/Code/digithings-ci
```

The checkout is the runner's own: the daemon runs the code in it and checks
the pull requests against it. A dedicated clone on `develop` is the checkout to
point it at - not a working tree, not a linked worktree (see "The producer"
below).

`--dry-run` prints the rendered plist and touches nothing: no write, no bootout.

## The producer

Two launchers can post the pre-merge receipt: the launchd daemon on this Mac
and the CI container's worker. The daemon is the one that runs here, and it
runs from a dedicated clone of this repository on `develop` - not from a
seat's shell, and not from a linked worktree of somebody's checkout:

```
git clone --branch develop git@github.com:digithings-ai/digithings.git ~/Code/digithings-ci
scripts/local-ci/install.sh --self-update ~/Code/digithings-ci
```

`install.sh` refuses a linked worktree (`.git` is a file) unless
`--allow-worktree` is passed: a linked worktree is a checkout somebody else
works in, and a daemon that moved it would move their work with it.

`--self-update` is the operator's word that the runner may keep that checkout
on `origin/develop` by itself. It is refused unless the checkout is a dedicated
clone: its own `.git` directory (so not a linked worktree), on `develop`, a
clean tree, and no commits of its own on top of `origin/develop`. A working
tree that is clean and carries no local commits is not caught by a separate
test, so point the daemon at a dedicated clone and not at the tree you work
in. The install records the word in
`~/.config/digithings/state/local-ci-runner.json`:

```json
{"main": "/Users/<you>/Code/digithings-ci", "self_update": true}
```

Without that mark the runner never moves the checkout: `LOCAL_CI_MAIN`
defaults to a plain working tree, and a runner that fast-forwards somebody's
working tree moves their files with it. The mark is written by `install.sh`,
with `self_update` true only for a real clone on `develop`.

The refresh fast-forwards the checkout and does nothing else: it never touches
a linked worktree, it only ever moves the `develop` branch of the marked
checkout, and it leaves the checkout alone when the update would not be a
fast-forward (a local commit, or dirty files the incoming commits touch). The
incoming commit is checked before the switch: the runner it carries must
compile and it must still carry the launch guard, because the next tick
executes whatever landed on `develop` and a broken runner would stop the only
pre-merge producer. The guard has to keep the interface the runner calls
(`enforce(runner_path, ...)`), because a guard that cannot be called stops the
runner the same way. A daemon running an old commit produces old receipts, so
the runner refreshes the code that posts them.

The seat-shaped install (`install.sh --allow-worktree`) is a temporary measure
for the window in which the daemon is not running. It does produce receipts,
but it depends on a seat's timing and it leaves the queue to whoever acts: it
is not a receipt policy. It does not refresh either, because a linked
worktree is never refreshed and the mark it gets says so: the runner keeps
posting receipts from the commit it was installed on, and the log says so. A
refusal of that kind is structural, so the log line repeats at most once every
fifteen minutes.

Two things keep a receipt from being lost when a run dies (DIG-5135):

- **the claim ledger**: a run takes the claim on a head before it posts the
  `pending` row, and releases it when the verdict is posted. A run that dies
  leaves the claim behind, and the next tick reads it, sees that the holder is
  gone, and queues the head again. A `pending` row is a claim, never a verdict.
  A holder that is alive keeps its head: an old `pending` row never takes a
  running head away, and a head whose claim is held is neither queued nor
  skipped, and its claim is released by the run that took it, not by the
  queue. Two things do take a live claim away, and both are the sign that the
  run is no longer the run the queue waits for: a claim held for longer than
  eight hours - longer than the slowest gate run the code's own step timeouts
  allow, about 4.75 h - and a pid the kernel has handed to another process
  since the claim was written. A holder that has exited and is only waiting to
  be reaped is not a living holder either, and its head is queued again. A
  `pending` row with no ledger entry - posted by a runner that predates the
  ledger, or by the CI container, which keeps its own state directory - is
  given six hours before it is treated as lost, which is longer than the
  longest gate run, so a container that is still gating a head is not overtaken
  while it works. A claim is released by the run that took it: a run that was
  taken over never deletes the claim of the run that replaced it.
- **the fair order**: the queue is by arrival, oldest first, so the pull
  request that arrived first is served first. It used to be newest first,
  which meant a PR that arrived early waited behind every later arrival and
  could wait for days for a required check. The order is by arrival and not by
  last activity: a PR that is commented on is not pushed back to the end. The
  `review-applied` lane is served in the same order, so a pull request that
  waits for its review verdict does not wait behind every later arrival.
- **one run per head**: an explicit `--pr N` run is a run like any other and
  does not start on a head another run is checking, because two runs on one
  head post two `local-ci` rows on the required check.
- **a preview changes nothing**: a dry run reads the claim ledger and never
  writes to it, so `--dry-run` cannot spend a claim.
- **a row that says the post failed is not a verdict**: a head whose only row
  says `error` carries no receipt, so it is queued again and its claim is
  released. The `local-ci/app` row is a second context, not the required
  check: a refused app row is logged and the head keeps the receipt it
  earned on `local-ci`.
- **a metadata failure is re-checked, not re-committed**: a failure that names
  only `pr-title` and `pr-template` is the one class whose remedy does not touch
  the tree, so a corrected title or body queues the same head again - no new
  commit, and no review on the head goes stale for it (DIG-5695, PR #6513). The
  metadata a verdict judged is remembered in `metadata-recheck-<sha>` next to
  the gitleaks sentinel, so one edit buys one re-check and not one per tick. A
  failure that names any code gate keeps its row terminal: its remedy is a
  commit.

## The bun suites

The bun packages (`clients/digichat-tui`, `clients/digiquant-tui`,
`clients/digivoice-tui`, `clients/digichat-devkit`, `packages/surface-config`,
`packages/hero-banner`, plus the pre-move `digivoice/tui`) declare
`"test": "bun test"`. Their only lanes were `test-bun-suites.yml` and
`test-clients-tui.yml`, both retired with Actions (DIG-3604 / DIG-4454), so
between then and DIG-5203 the required `local-ci` check ran no bun test at all:
PR #6271 carried a green receipt while digichat-tui's suite (70 pass, 1 fail)
only ever ran by hand.

The gate reads the suite list from `scripts/ci_paths.yaml` `bun_suites`, and
also scans `clients/*` and `packages/*` for a manifest that declares
`"test": "bun test"`, so a new client is gated on its first PR instead of
waiting for somebody to edit the list. The `clients/**` entry in `bun_suites`
is what fires the gate for those new clients. When a PR touches any of those
paths it runs every suite, in order:

- `bun --version` must equal `BUN_PIN`, or no suite runs and the receipt says
  `bun-version` (an unpinned tool changing under a green build is the
  #1701/#1705/#1711 failure mode);
- a standalone bun package (the clients, `digivoice/tui`) installs from its
  committed `bun.lock` with `--frozen-lockfile`; a package that is a workspace
  of the root `package.json` (`packages/*`, `apps/*`) skips the install,
  because `bun install` there would walk up to the repo root and install the
  whole monorepo;
- `bun run test` runs the manifest's own script, in the suite directory.

One suite failing does not stop the others: the receipt names the failed gate
(`bun:digichat-tui`) and the log carries every suite's output. On success the
description names the suites that ran, or says `bun: none` when no `bun_suites`
path changed. The description is capped at 140 characters, so the names are
dropped for a count before they can be cut in half; the run log always has them
in full.

This is the runner, not the agent: the launchd job is frozen per DIG-5157, so
the gate reaches the host when the host copy is synced, not by reloading the job.

## Invariants this script is built around

- **A skip is never silence.** A memory or disk guard that forces a skip posts
  `failure` on the queued PRs, so merges block loudly instead of passing quietly.
- **A lost run is not a lost receipt.** The claim ledger names the holder of
  every head being checked, so a run that dies leaves a head that is queued
  again instead of a PR that waits for ever (DIG-5135).
- **The first arrival goes first.** The queue is by arrival and oldest first,
  so a PR that arrived early is not overtaken by every later arrival
  (DIG-5135).
- **A running head is not taken away.** A claim held by a living run is left
  alone, whatever age its `pending` row carries, unless the claim has outlived
  the worst case of a gate run (eight hours, deliberately longer than the life
  of the tick lock, so a tick that took over a stale lock still leaves a live
  head alone) or its pid now belongs to another process
  (DIG-5135).
- **The refresh is never retried on every tick.** A refresh that fails - no
  network, a commit that does not fast-forward, an incoming runner that does
  not compile - consumes its window like a success does, because the refresh
  runs inside the tick lock and a fetch that always fails would otherwise hold
  the lock on every tick (DIG-5135).
- **The runner only moves the checkout it was given.** The refresh
  fast-forwards the checkout that `install.sh` marked as the runner's own, and
  only that one; it never touches a working tree that belongs to somebody
  else, and it checks the incoming runner before it switches (DIG-5135).
- **Fork code never executes here.** Fork PRs get a `failure` naming the re-push
  path a maintainer must use.
- **A skipped suite names itself.** The success receipt names every bun suite
  that ran, or says `bun: none` when no `bun_suites` path changed, so a PR that
  proves nothing about a client says so instead of reading green (DIG-5203).
- **Fails closed on a missing input.** If the review record or the PR body cannot
  be read, the check fails; it does not assume the best.
- **A stalled checkout is retried, not a verdict.** The checkout of the checks
  worktree gets minutes, not a quarter of an hour, and a checkout that stalls
  is retried in place once: a rebuild repeats the same lazy fetch that stalled,
  so a slow network is not a broken worktree. A checkout that lands on another
  HEAD is a broken worktree, and that one is rebuilt (DIG-5285).
- **A worktree the runner does not own is never rebuilt.** A rebuild removes
  files, so it is allowed only for a worktree of this repository, and only
  when it has no uncommitted changes (DIG-5285).
- **A rebuild keeps the caches.** `.venv` and `node_modules` are the two
  directories the clean step protects; a rebuild moves them aside and puts them
  back, so a repaired worktree does not turn into an hour of `uv sync` and
  `npm ci` (DIG-5285).
- **No step is waited on past its budget.** Every gate step has a wall-clock
  ceiling of `STEP_BUDGET` (180 s) and the ones that legitimately need longer
  name themselves in `STEP_BUDGETS` (gitleaks, `uv sync`, mypy, the worker
  dry-runs, the bun suites); an explicit `budget=` wins, and
  `LOCAL_CI_STEP_BUDGET` raises the default for the whole host. A step that
  overruns is killed by process group, recorded as `<step> exceeded <N>s and was
  killed`, and the tick moves on to the next step. Every step also writes
  `step=<name> seconds=<n> rc=<n>` to its log, so the next investigation reads
  the duration table instead of re-measuring by hand (2026-10-26).
- **Static gates, plus two path-gated lanes.** The worker dry-run build and the
  bun suites run only for the paths that need them. Per-package pytest suites,
  compose validation, npm and pip audit, token canary, secret staleness,
  invite-key rollout and cron dispatch are not gated here (DIG-3605 owns the rest).

## Copyright and secrets

Nothing secret is printed, logged or committed. Logs live under
`~/.config/digithings/logs/local-ci/`; state and the tick lock under
`~/.config/digithings/state/`.

## Keeping the job loaded

This script installs the runner only. The job that keeps it loaded and breaks a wedged
tick is `dt-daemon-liveness`, published in the private `digiforge` repository at
`scripts/dt-daemon-liveness` (DIG-4478). Install that alongside, or a stopped runner looks
exactly like an idle one.
