# digiquant host runner (DIG-2915)

Run the digiquant batch cadence on Chris's Mac under launchd, instead of inside the
`digiquant-runner` Cloudflare container. Parent epic: DIG-2904 "Cloudflare cost
minimum".

This page describes the host path. The job catalogue, the container, the kick API and
the secrets on the Worker are still described in
[digiquant-runner.md](digiquant-runner.md); nothing there changed.

## Status: what is and is not true yet

True after this change lands:

* `scripts/digiquant-host-runner/` can resolve, run and record every job in
  `apps/digiquant-runner/commands.json` on this Mac.
* `install.sh` can render one launchd clock per enabled container cron and install
  them. Loading them is Chris's call and is never done by an agent.
* Each run leaves a log and a JSON record, so a silent launchd job cannot hide.

Not true yet, deliberately:

* `digithings-cron` still dispatches to the container. The container is still
  deployed and still runs the cadence. Removing it is the follow-up PR, and it must
  wait until the Mac clocks have run green for a full cycle.
* `--publish` (artifact upload to `pipeline-runs/<job>/<run_id>/`) is opt-in because
  `boto3` is not in the host environment. The jobs still write their own results to
  R2/D1/Supabase through the env the catalogue already allows.
* `allocation-shadow` has no clock: it is dispatched from
  `.github/workflows/pipeline-digiquant-allocation-shadow.yml`, not cron. It is
  runnable by hand here and needs no env.

## One catalogue, two executors

`apps/digiquant-runner/container/exec_job.py` stays the only implementation of the
step plan: `plans_for`, `build_child_env`, `classify_step_exit`,
`step_wait_seconds`. `run_job.py` imports that module from the checkout and uses it,
so a gate like `run_writers`, a `continue_on_error`, or an `always` step cannot mean
one thing in the image and another on the Mac.

What the host adds, because launchd does not provide it:

| Concern | Container | Host |
| --- | --- | --- |
| Overlap | Durable Object ledger plus a twin `POST /run` 409 | `flock` per `concurrency` key, exit 75 `already_running` |
| Secrets | Worker bindings | env file outside the repo, mode 600, refused otherwise |
| Deadlines | Worker watchdog | per-step and per-job deadline, kills the process group |
| Image paths | `/opt/runner/*.py` | rewritten to `apps/digiquant-runner/container/*.py` |
| Artifacts | `publish` / `publish_always` | opt-in `--publish`, needs `boto3` |
| Record | `GET /runs/:run_id` | `~/.config/digithings/state/digiquant-host-runner/<job>.json` |

## Files

| File | What it is |
| --- | --- |
| `run_job.py` | The executor: one job, its plan, a lock, a log, a record |
| `schedule.py` | The launchd clock table, and the renderer for one plist per clock |
| `com.digithings.digiquant-job.plist.template` | The plist every clock is rendered from |
| `install.sh` | Render, lint, install, `--status`, `--unload`, and an explicit `--load` |

## Run one job by hand

```sh
scripts/digiquant-host-runner/run_job.py --list
scripts/digiquant-host-runner/run_job.py market-data-refresh --dry-run
scripts/digiquant-host-runner/run_job.py execution-cron-check --json
scripts/digiquant-host-runner/run_job.py research-metrics --arg date=2026-10-20 --json
```

`--dry-run` prints the resolved argv and the env *names* a job may receive. It never
prints a value, so it is safe to paste into a ticket.

A real run needs the checkout's Python environment. The plans call
`uv run --frozen --no-sync`, so nothing is installed when a clock fires: the checkout's
`.venv` must already hold the packages the image holds. The workspace root declares no
dependencies of its own, so a plain `uv sync --frozen` leaves `.venv` empty and every
clock fails its first step with `ModuleNotFoundError`. Build it once, from the same lock
the image uses (the second sync is `--inexact` so it keeps the `psycopg` the first one
installed, as the Dockerfile comment explains):

```sh
cd /path/to/clone-on-develop
/opt/homebrew/bin/uv sync --frozen --package digiquant --extra prices --extra research --extra nautilus --no-dev
/opt/homebrew/bin/uv sync --frozen --package digigraph --extra checkpoint-postgres --no-dev --inexact
```

`install.sh --install` refuses a checkout whose `.venv` cannot import `polars`, `psycopg`
and `nautilus_trader`, so a missing environment cannot become 13 broken clocks. Rebuild
the environment after a `git pull` only when `uv.lock` changed.

Exit codes: `0` success, `1` the job failed, `2` usage, `75` another run holds the
lock (a skip, not a failure), `78` the env file is missing, unreadable or readable by
group/others.

**The checkout replaces the image pin.** The container baked `code_ref: main` into the
image; here the code is whatever the checkout at `develop` holds, and the installer
refuses any other branch on purpose (clocks outlive sessions and branches get deleted).
For `execution-cron-check` that is a real difference: the container ran the `main`
probes, the Mac runs `develop`. Check that job first when the clocks go live.

## The env file

`~/.config/digithings/digiquant-host-runner.env`, mode 600. Outside the repository,
never committed, never named in a public ticket with a value.

```sh
# create it, then paste values one per line, never through the shell history
umask 077 && touch ~/.config/digithings/digiquant-host-runner.env
chmod 600 ~/.config/digithings/digiquant-host-runner.env
```

Format: `NAME=value`, `#` comments, no shell expansion, optional `export` prefix. A
line that is not an assignment is refused, because a typo must not silently drop a
credential.

The names are the union of the catalogue's `env` lists:

```
CORE_SUPABASE_URL                     CORE_SUPABASE_SERVICE_KEY
CORE_POSTGRES_URI                     R2_ACCOUNT_ID
R2_BUCKET                             R2_ACCESS_KEY_ID
R2_SECRET_ACCESS_KEY                  CLOUDFLARE_EMAIL_API_TOKEN
CLOUDFLARE_ACCOUNT_ID                 NOTIFY_FROM
DIGIQUANT_DIGIKEY_API_KEY             OPENROUTER_API_KEY
CHEAPERINFERENCE_API_KEY              CHEAPERINFERENCE_API_BASE
LANGSMITH_API_KEY                     DIGI_OTEL_HEADERS
```

The same values are already on the Worker (`wrangler secret list` names them without
showing values). Provisioning them on the Mac is the operator's step; this ticket
does not write, copy or read a secret. `FRED_API_KEY` stays unset, as it is on the
Worker.

A missing name is a warning in the record (`missing_env`), not a refusal: some names
are optional depending on the gates (`run_writers`, `date`). Add `--require-env NAME`
to make one mandatory.

## Clocks

The clocks are the enabled container rows in `apps/digithings-cron/src/jobs.ts`, with
their crons. `tests/scripts/test_digiquant_host_runner.py` parses `jobs.ts` and fails
when the table drifts, so a moved Worker clock cannot leave a stale one here.

| launchd label | Job | UTC cron |
| --- | --- | --- |
| `com.digithings.digiquant.market-data-refresh-morning` | `market-data-refresh` | `0 13 * * *` |
| `com.digithings.digiquant.market-data-refresh-evening` | `market-data-refresh` | `30 21 * * *` |
| `com.digithings.digiquant.checkpoint-archive` | `checkpoint-archive` | `30 13 * * *` |
| `com.digithings.digiquant.prices-at-open-13` | `prices-at-open` | `40 13 * * MON-FRI` |
| `com.digithings.digiquant.prices-at-open-14` | `prices-at-open` | `40 14 * * MON-FRI` |
| `com.digithings.digiquant.prices-fx-refresh` | `prices-fx-candles` | `19 */2 * * MON-FRI` |
| `com.digithings.digiquant.prices-fx-refresh-sun` | `prices-fx-candles` | `19 22 * * SUN` |
| `com.digithings.digiquant.prices-eod-macro` | `prices-eod-macro` | `27 21 * * MON-FRI` |
| `com.digithings.digiquant.house-run-09` | `house-run` | `17 9 * * MON` |
| `com.digithings.digiquant.research-metrics` | `research-metrics` | `5 22 * * *` |
| `com.digithings.digiquant.tearsheets` | `tearsheets` | `12 0 * * *` |
| `com.digithings.digiquant.onchain` | `onchain-bitview` | `40 22 * * *` |
| `com.digithings.digiquant.execution-cron-check` | `execution-cron-check` | `15 12 * * *` |

launchd's `StartCalendarInterval` is local time and has no time-zone field, so
`schedule.py` converts each row against the Mac's zone rules at render time and keeps
the UTC cron in the plist comment. A clock that crosses a DST change keeps the old
local hour: `install.sh --status` reports it as `stale`, and re-installing (with
Chris's `--load`) fixes it. Nothing here writes a new clock minute.

## Install, status, rollback

```sh
scripts/digiquant-host-runner/install.sh --list       # labels, jobs, UTC crons
scripts/digiquant-host-runner/install.sh --status     # installed? loaded? current or stale?
scripts/digiquant-host-runner/install.sh --dry-run    # the rendered plists, nothing changed
```

Installing is Chris's call, because loading a launchd job is:

```sh
scripts/digiquant-host-runner/install.sh --install --load /path/to/clone-on-develop
scripts/digiquant-host-runner/install.sh --unload
```

The installer refuses a linked worktree, a branch that is not `develop`, a missing
env file, an env file readable by group/others, and a missing `/opt/homebrew/bin/uv`,
by default. A re-install keeps the previous plist as `.bak.<stamp>` and restores it if
a load fails.

Rollback is `--unload`. It does not touch the container: the Worker clocks were never
flipped by this change, so unloading the Mac clocks returns the cadence to the
container exactly as it was.

## Watching it

* Per-run log: `~/.config/digithings/logs/digiquant-host-runner/<job>-<run_id>.log`
* Per-job record: `~/.config/digithings/state/digiquant-host-runner/<job>.json`
* Append-only history: `~/.config/digithings/state/digiquant-host-runner/history.jsonl`
* launchd's own stdout/stderr, for a run that dies before `run_job.py` starts:
  `~/.config/digithings/logs/digiquant-host-runner/com.digithings.digiquant.<label>.{stdout,stderr}.log`

A `skipped` record with `reason: already_running` is the lock doing its job: the
morning and evening refreshes share one concurrency group, and so do the two intraday
FX clocks. It is not a failure.
