# digiquant house-run Phase 3 Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Run the daily house research command `house-run` on the existing digiquant-runner container, with digithings-cron as the only clock, an R2 skip ledger, and a secrets-empty `allocation-shadow` follow-on.

**Architecture:** One Worker, one Durable Object id (`runner-v1`), one container class (`DigiQuantRunnerContainer`), one image, `instance_type = "standard-2"`. The class already runs prices, market-data, tearsheets, on-chain, metrics, and the execution probe. Phase 3 adds `house-run` and `allocation-shadow` to that same class. The image grows only by the imports `python -m digiquant.portfolio.chain` actually needs. Idle `sleepAfter` stays `2m`, so the instance reaps after the queue drains. There is no second class and no warm pool.

**Tech Stack:** Cloudflare Workers + Containers (`@cloudflare/containers`), wrangler, Python 3.12, uv, Vitest, the existing stdlib `exec_job.py`. Account id stays `ae2ea3eb4ce5f7cc9bec1478f6e60e15`.

**Status:** plan only. Written 2026-09-30 against `origin/develop` @ `6840301e5` (squash of #4822). This document does not flip cron, put secrets, or deploy. Epic [#4761](https://github.com/digithings-ai/digithings/issues/4761) is closed on GitHub; Phases 3–5 are still unfinished. Implementation PRs say `Part of #4761` and do not close the epic.

---

## Chris lock — one class, standard-2

Locked for this plan. An implementation PR that violates it is out of scope.

| Decision | Locked value |
|---|---|
| Container class | `DigiQuantRunnerContainer` only. `wrangler.toml` keeps a single `[[containers]]` entry. |
| Instance type | `instance_type = "standard-2"` (epic table: 1 vCPU, 6 GiB memory, 12 GB disk). |
| Image | One `Dockerfile.digiquant-runner`. Slim the `uv sync` / extras / `COPY` set until the chain imports on that disk. |
| Instances | `max_instances = 1`. Durable Object id stays `runner-v1`. |
| Idle | `sleepAfter = "2m"` when the ledger has no lock and no queue. No always-on warm pool. |
| Second class / standard-3 / standard-4 | Rejected as the design. A note in [Risks](#risks) records them as a doomed escape hatch that this phase does not implement. |

The epic's Phase 3 paragraph names a third class `DigiQuantHouseContainer` at `standard-4` and `uv sync --frozen --all-packages --all-extras` as the build. That sizing is **not** the plan. Chain business logic is unchanged: do not edit `digiquant/src/digiquant/portfolio/chain.py` or the research graph. The workflow's step order, caps, and env names below are still the behavior to reproduce.

Why one small class: every live cadence shares this Worker. A larger `instance_type` would raise the memory-time rate for prices and tearsheets as well as house-run. A second class is a second image to build, pin, and roll back, and a second instance that can stay awake beside the first. Chris rejected both on cost and maintenance. The idle bill is the `2m` tail after the last lock clears, plus the `30m` inactivity window that the 60s heartbeat renews only while work is held (`apps/digiquant-runner/src/runner.ts`).

---

## Global constraints

- Digi product names stay lowercase in prose, docs, commits, and PR text.
- Polars only. Pydantic v2. Do not add pandas.
- Do not edit live-trading paths or `digiquant/brokers/`.
- Do not put broker credentials, Alpaca keys, or `--execute` on the runner.
- Do not edit `digiquant.portfolio.chain` (or `digiquant/src/digiquant/research/` logic). The chain CLI is called, not rewritten.
- Code pin stays released `main` baked into the image. Hot path stays `uv run --frozen --no-sync`. Do not `uv sync` on a tick.
- `GITHUB_OVERRIDE_JOBS` empty means migrated jobs never call `api.github.com`.
- Do not add a `schedule:` key to any workflow.
- No public hostname. `workers_dev = false`. No `[[routes]]`.
- No `FRED_API_KEY`. No `GH_ISSUE_TOKEN`. The runner does not file GitHub issues (`commands.json` has no `failure_issue`; `commands.test.ts` already asserts that).
- #4822 stays in force: same-command `POST /run` returns 409 while that command's status is `running` (`_running_command` in `exec_job.py`); artifact publish is bounded by `PUBLISH_TIMEOUT_SECONDS = 120`; the DO keeps the concurrency lock while `/status` is still non-terminal (`pollLock` in `runner-session.ts`). Phase 3 must not release that lock early and must not start a second `house-run` (or a second `market-data-refresh`) in the same container.
- `house_schedule_skip.py` stays the GitHub Actions gate. Add one comment pointing at the R2 ledger. Do not change which Actions events count as a prior success.

---

## Non-goals

- Phase 4 and Phase 5 (checkpoint-archive, smokes, provider-review, maintenance, twelve-x).
- Rewriting `digiquant.portfolio.chain` or changing refresh-scope business rules.
- Repairing the allocation-shadow `workflow_run` name filter. `.github/workflows/pipeline-digiquant-allocation-shadow.yml` listens for `Pipeline: dashboard research`. The live house workflow name is `Pipeline: digiquant research`. Leave that mismatch. Do not edit `TRUSTED_SOURCE_WORKFLOWS` in `digiquant/scripts/research/check_allocation_shadow_isolation.py`.
- `FRED_API_KEY`, Gloomberb macro changes, or any new macro source.
- `GH_ISSUE_TOKEN` on the runner. Failure-issue titles `digiquant-daily-failure` and `digiquant-daily-cancelled` stay byte-identical **inside** `.github/workflows/pipeline-digiquant.yml` for the override path. The container path does not open or comment on those issues. `timed_out` is a job status on `GET /v1/jobs/:id`, not a GitHub title from this Worker.
- A second container class, `standard-3`, `standard-4`, or `max_instances` above 1.
- Deleting `repository_dispatch` type `digiquant-baseline` from `pipeline-digiquant.yml`. Phase 3 stops the cron from sending it. The workflow file remains the manual override.

---

## Current state (verified on `6840301e5`)

| Surface | What is true today |
|---|---|
| Class | `apps/digiquant-runner/wrangler.toml` — one `[[containers]]`, `class_name = "DigiQuantRunnerContainer"`, `instance_type = "standard-2"`, `max_instances = 1`. Comment on lines 20–23: do not add `OPENROUTER_API_KEY`, `DIGIQUANT_DIGIKEY_API_KEY`, or `LANGSMITH_API_KEY` until the house run. |
| Image | `Dockerfile.digiquant-runner` — `uv sync --frozen --package digiquant --extra prices --extra research --extra nautilus`. Copies `digibase`, `digikey`, `digifetch`, `digiquant`, `scripts/refresh_market_data_r2.py`, `scripts/backfill_market_data_r2.py`, `scripts/execution_cron_check.py`, `exec_job.py`, `commands.json`. Nautilus wheel size already recorded in the Dockerfile header: 182608916 bytes. No curl, no tini. `CMD` is `python /opt/runner/exec_job.py serve`. |
| Catalog | `apps/digiquant-runner/commands.json` has market-data-refresh, prices-fx-candles, prices-at-open, prices-eod-macro, prices-fx-refresh-writers, onchain-bitview, execution-cron-check, research-metrics, tearsheets. No `house-run`. |
| Tests that must move | `apps/digiquant-runner/src/commands.test.ts` expects `assertKnownCommand("house-run")` to throw. `apps/digiquant-runner/src/runner.test.ts` uses `command: "house-run"` as the unknown-command 400. |
| Cron | `apps/digithings-cron/src/jobs.ts` lines 168–174: `rd("house-run-09"…"12", "17 9/10/11/12 * * *", DIGITHINGS, "digiquant-baseline")`. Comment: house-run stays `repository_dispatch`. |
| Dispatch | `kind: "container"` POSTs `RunJobRequest` to `RUNNER`. `force` on `POST /kick` skips the ET open gate only (`apps/digithings-cron/src/index.ts`). It is not forwarded to the runner. Scheduled ticks send `args: {}`. |
| Ledger | No R2 `success.json`. Skip-if-done for GHA is `digiquant/scripts/research/house_schedule_skip.py` (counts `schedule` and `repository_dispatch` only). |
| SIGTERM | `exec_job.py` `_on_sigterm` marks status `failed`, `reason: "sigterm"`, kills the process group, exits 143. It does not write R2. |
| Publish | `_publish` uploads **files** to `pipeline-runs/<command>/<run_id>/<filename>` via boto3. `_publish_bounded` joins 120s. Publish runs only when the step list succeeded. |
| Concurrency | `MAX_INFLIGHT = 2` in `runner-session.ts`. Same `concurrency` string returns `already_running`. A different group can run beside it, up to 2 subprocesses in the one container. Queue promotes on the 60s alarm. |
| Activity | `sleepAfter` is `2m` idle and `30m` while `hasActiveWork()` (any lock **or** any queued run). Heartbeat is `Container.schedule` → `heartbeat` every 60s and calls `GET /status`. `onActivityExpired` renews only when work is held; otherwise it calls `super` and the platform reaps. |
| House workflow | `.github/workflows/pipeline-digiquant.yml` name `Pipeline: digiquant research`. No `schedule:` (removed in #3579). `repository_dispatch` types `[digiquant-baseline]` and `workflow_dispatch`. Concurrency group `digiquant-pipeline`, `cancel-in-progress: false`. `timeout-minutes: 240`. |
| Pipeline env file | `.github/digiquant-pipeline.yml` `env:` map. Root `.dockerignore` ignores `.github` and `scripts/` except the re-includes already listed. The pipeline file is **not** in the image today. |
| Allocation shadow | `workflow_run` on `Pipeline: dashboard research` only. First real step is `check_allocation_shadow_isolation.py`. Write-denied: no Supabase, provider, broker, or checkpointer secrets. |
| Chain resume id | `resolve_run_id` in `chain.py` returns `GITHUB_RUN_ID` or `f"{cadence}-{run_date}-local"`. `--resume-run-id` is that prior id (`chain.py` help text: "its GITHUB_RUN_ID"). Do not change this function. The container must set `GITHUB_RUN_ID` to the runner `run_id` for the house child so the checkpoint thread is the runner UUID, then pass that same string as `--resume-run-id` after SIGTERM. |

---

## Measure the image before cutover

Do this before changing the `uv sync` line that production builds, and before any cron flip. Record the numbers in the implementation PR. Do not invent a size.

Disk budget is the platform `standard-2` disk from the epic table: **12 GB for the whole instance**, image plus writable layer (`/tmp/runner`, `artifacts/`, uv cache). Cutover bar:

- `docker image inspect` `Size` is strictly under 12 GiB, and
- a stopped-command `docker run` shows at least **2 GiB free** on `/` before any job writes.

If the narrow sync misses that bar, stop. Do not change `instance_type`. Do not add a class. Ask Chris. The [last-resort note](#risks) is not a license to upsize inside the implementation PR.

### Probe ladder

Work from a clean tree. Do not `wrangler deploy`.

```bash
# 0. Current production image (baseline). Expect chain import to fail.
docker build -f Dockerfile.digiquant-runner -t digiquant-runner:phase2 .
docker image inspect digiquant-runner:phase2 --format 'phase2 Size={{.Size}}'
docker run --rm digiquant-runner:phase2 python -c \
  "import shutil; u=shutil.disk_usage('/'); print(f'phase2 total={u.total} free={u.free}')"
docker run --rm digiquant-runner:phase2 python -c "import digiquant.portfolio.chain"
```

Save the `ModuleNotFoundError` module name. That name is the next `COPY`, not a guess.

```bash
# 1. Add only the missing workspace member directory to COPY, then:
uv sync --frozen --package digiquant --extra prices --extra research --extra nautilus
# If digigraph is the missing import, a second frozen sync keeps the first venv:
uv sync --frozen --inexact --package digigraph --extra checkpoint-postgres
docker build -f Dockerfile.digiquant-runner -t digiquant-runner:house-candidate .
docker image inspect digiquant-runner:house-candidate --format 'candidate Size={{.Size}}'
docker run --rm digiquant-runner:house-candidate python -c \
  "import shutil; u=shutil.disk_usage('/'); print(f'candidate total={u.total} free={u.free}')"
docker run --rm digiquant-runner:house-candidate python -c "import digiquant.portfolio.chain; print('chain import ok')"
```

Repeat step 1 for the next missing module only. `digigraph`'s `checkpoint-postgres` extra is the one the workflow comment names (`langgraph-checkpoint-postgres`, resume path #665). Add it when the import asks for it, via the `--inexact` second sync above.

`uv sync` accepts a single `--package`. That is why `.github/workflows/pipeline-digiquant.yml` uses `--all-packages --all-extras`. Do not start there.

```bash
# 2. Only if step 1 still cannot import the chain: one all-packages sync
#    with the named extras, still not --all-extras.
uv sync --frozen --all-packages --extra prices --extra research --extra nautilus --extra checkpoint-postgres
# 3. Last probe on this class, still standard-2. Record Size and free bytes.
#    If free < 2 GiB or Size >= 12 GiB, stop and ask. Do not deploy this tag.
uv sync --frozen --all-packages --all-extras
```

Never add `brokers-alpaca`, `brokers-ibkr`, `dev`, `visualization`, or `mcp` unless the import probe names a module that lives only in that extra.

Also confirm the chain module is the only new entrypoint:

```bash
docker run --rm digiquant-runner:house-candidate \
  python -c "import digiquant.prices, digiquant.web_search; print('siblings ok')"
```

`validate-providers.py` and `check_allocation_shadow_isolation.py` already live under `digiquant/`, which the image copies.

---

## Scale-to-zero

The platform reaps a container after `sleepAfter` with no incoming request. A running `uv` process does not count as activity. The existing alarm is what keeps a job alive, and what lets it die afterward.

| Knob | Value | Effect |
|---|---|---|
| `max_instances` | `1` | One instance. A second job does not boot a second machine. |
| DO id | `runner-v1` | One ledger. |
| `sleepAfter` idle | `2m` | After the last lock drops and the queue is empty, `applyActivityWindow` sets `2m`. The next `onActivityExpired` calls `super` and the instance is gone. |
| `sleepAfter` while busy | `30m`, renewed | `hasActiveWork()` is true while any concurrency lock **or** any queued run exists. Heartbeat `GET /status` every 60s (`HEARTBEAT_MS`) counts as a request, so a 240 minute house-run is not reaped at 2 minutes. |
| Cold start | next tick pays boot | After reap, the next price or house kick starts the container again. That delay is accepted. Do not add a cron ping of `/healthz` to keep the instance warm. |
| Warm fleet | none | Do not raise idle `sleepAfter`, do not set `max_instances` above 1, do not add a second class "to keep prices warm during house". |

Bill shape: one `standard-2` for the house run (up to 14400s) plus any command still queued behind it, then a 2 minute idle tail. The `30m` figure is the inactivity window renewed by the heartbeat during work, not an extra half hour after exit. When the ledger is empty the window goes back to `2m`.

`scheduled()` in digithings-cron already returns after the POST. It must stay that way. A 240 minute await would die on the Workers cron wall.

---

## Concurrency

House-run is long (timeout **14400** seconds) on a 1 vCPU / 6 GiB instance. Today `MAX_INFLIGHT = 2` allows a different concurrency group (prices, market-data, tearsheets) to `startRun` in the same container while `digiquant-pipeline` is held. That is the stampede. It is also how a price tick could sit beside the chain and push the box into OOM.

**Recommended default, pending the [open question](#open-questions):** while a `house-run` lock is held, `accept()` queues every other command instead of starting it. `promote()` starts the queue only after that lock is gone, still capped by `MAX_INFLIGHT`. Same-group overlap stays `already_running` (house-run-10 does not stack on house-run-09). Do not drop ticks. Do not cancel the house run (`cancel-in-progress` stays false, matching the workflow).

Queued jobs keep `hasActiveWork()` true, so the single instance stays awake until the backlog drains, then the `2m` reap runs. That is one instance finishing work, not a fleet.

Skip-before-start (below) means house-run-10/11/12 after a success never enter the queue and never cold-start.

`allocation-shadow` is a follow-on command on this same class after house-run exit 0. It uses a different concurrency key (`digiquant-allocation-shadow`) so it does not look like a second house-run. It runs after the house lock is released, still inside the same instance, then the idle path reaps. It must not be a reason to keep `sleepAfter` at `30m` once its own lock clears.

#4822 interaction:

- The exclusive queue is in the DO **before** `port.startRun`. It does not weaken the container 409.
- `POST /run` still returns 409 when `_running_command(command)` finds a `running` status for that same command. A watchdog that used to drop the lock early must still refuse the twin writer.
- `_publish_bounded` stays 120s for file uploads. A house directory publish uses the same bound (see risks if the directory is large).
- `pollLock` still refuses to mark `timed_out` while remote status is non-terminal.

---

## House-run behavior

### Cron contract

Jobs `house-run-09` … `house-run-12` (`17 9 * * *`, `17 10 * * *`, `17 11 * * *`, `17 12 * * *`) become `kind: "container"`, `command: "house-run"`, `concurrency: "digiquant-pipeline"`, `timeoutSeconds: 14400`. Keep `workflow: "pipeline-digiquant.yml"` and `ref: "develop"` so `GITHUB_OVERRIDE_JOBS` can still `workflow_dispatch` that file (`cj()` in `jobs.ts`). Container `codeRef` stays `"main"`.

Ordinary ticks (the cron trigger, and `POST /kick` without `force: true`) send:

```json
{ "refresh_scope": "none", "run_date": "<UTC today YYYY-MM-DD>" }
```

The Worker computes `run_date`. It is not a static string in `jobs.ts`.

Only `POST /kick` with `"force": true` may set `refresh_scope` to something other than `none`, `dry_run` to `"true"`, or `resume_run_id`. Any other caller that sends those keys has them stripped. Omit `dry_run` rather than sending `"false"`. Pass `force: "true"` inside `args` only on that forced kick, so the runner skip gate can see it. Scheduled ticks never set `force`.

A forced kick still uses the UTC `run_date` unless the kick args include one.

### Skip, success, interrupted

Keys in bucket `digithings-archive` (the existing `R2_BUCKET`):

| Key | Writer | When |
|---|---|---|
| `pipeline-runs/house-run/<YYYY-MM-DD>/success.json` | Runner Worker / DO, not the chain | House-run status becomes `succeeded` (exit 0). Body `{"run_id","finished_at","git_sha"}`. |
| `pipeline-runs/house-run/<YYYY-MM-DD>/interrupted.json` | Container SIGTERM path in `exec_job.py` | Body `{"resume_run_id","run_date"}`. `resume_run_id` is the runner `run_id`, which the child saw as `GITHUB_RUN_ID`. |
| `pipeline-runs/house-run/<run_id>/<relative path>` | Container publish | Files under `artifacts/` for that run. |

Skip gate runs in `apps/digiquant-runner/src/index.ts` **before** `getContainer` / `stub().fetch`, so a hit does not cold-start. If `command == "house-run"` and `args.force != "true"` and `success.json` exists for `args.run_date`, log `skipped: house_already_succeeded` and return `202` with `{ "ok": true, "run_id": "<id from the object or empty>", "status": "skipped" }`. `apps/digithings-cron/src/dispatch.ts` `isContainerSuccess` treats `skipped` as success so the cron tick does not throw.

If the ledger binding is missing, house-run returns 500 `house_ledger_unconfigured` and does not start. A missing ledger must not double-spend the LLM chain. Other commands ignore the ledger.

A same-day GitHub Actions success still does not write this key. Say that in the runbook (already true in `docs/ops/digiquant-runner.md`).

On SIGTERM, after the status file is marked `reason: "sigterm"`, upload `interrupted.json` best-effort, then kill the group and exit 143 (existing behavior). The next house-run that did not receive an explicit `resume_run_id` reads that key for the same `run_date` and passes `--resume-run-id`. An explicit kick arg wins. A `success.json` for that date means the skip gate never starts the container, so the interrupted object is unused that day.

### Steps, in order

Copied from `.github/workflows/pipeline-digiquant.yml`. The chain CLI flags stay identical.

1. Load `.github/digiquant-pipeline.yml` `env:` into the child environment for this command. Re-include only that file in `.dockerignore` (`!.github/digiquant-pipeline.yml`) and `COPY` it. Do not copy the rest of `.github` except the one allocation-shadow workflow file in the next section. Keys today: `DIGIQUANT_MODEL_TIER`, `DIGI_HOUSE_UPSTREAM`, `DIGIQUANT_MAX_ANALYSTS`, `DIGIQUANT_MAX_TOOL_ROUNDS`, `DIGIQUANT_ONCHAIN_POSITIONING`, `DIGIQUANT_POSITION_RISK_FIELDS`, `DIGIQUANT_MARKET_DATA_BACKEND`, `DIGI_CHECKPOINTER`, `LANGSMITH_TRACING`. Parse the `env:` block in `exec_job.py` with the stdlib (the unit test stays PyYAML-free). Unknown keys in that block still pass through.
2. Fed rate odds. Non-zero is a warning (`continue_on_error: true`), not a failed job.
   - `dry_run=true`: `uv run --frozen --no-sync python -m digiquant prices fetch-macro --sources fedprob --manifest digiquant/src/digiquant/research/config/macro_series.yaml --dry-run`
   - otherwise: the same argv with `--supabase` instead of `--dry-run`.
3. `uv run --frozen --no-sync python digiquant/scripts/research/validate-providers.py --skip-dry-run` with a 600 second step cap.
4. Wake `https://key.digithings.ai/healthz` and `https://search.digithings.ai/healthz`, 12 attempts, 10 second timeout each, sleep 5. Non-fatal (exit 0 even if both stay down). The image has no `curl`. Implement this as `apps/digiquant-runner/container/wake_stack.py` using `urllib.request`. Do not `apt-get install curl`.
5. `python -m digiquant web-search healthcheck`, 6 attempts, sleep 10. Fatal if all fail (`apps/digiquant-runner/container/web_search_preflight.py`).
6. Up to 2 attempts of `python -m digiquant.portfolio.chain --cadence daily --run-date "$RUN_DATE" --refresh-scope "$REFRESH_SCOPE"` via `apps/digiquant-runner/container/house_chain_step.py`. Per-attempt cap 100 minutes (`timeout` in the script, `SIGKILL` 30s after). Sleep 300 seconds before attempt 2. Set `DIGIQUANT_ATTEMPT` to `1` or `2` in the child env for that attempt. Also set `DIGILLM_PROVIDER_MAX_ATTEMPTS=2`, `DIGILLM_EMPTY_RETRY_MAX=1`, `DIGILLM_MAX_CONCURRENT_CALLS=8`, `DIGIQUANT_SHADOW_ARTIFACT_MODE=export`, `DIGIQUANT_SHADOW_ARTIFACT_DIR=artifacts`, `LANGSMITH_PROJECT=digiquant-baseline`, `GITHUB_RUN_ID=<runner run_id>`. Optional `--dry-run` when `dry_run=true`. Optional `--resume-run-id` when the arg or `interrupted.json` has one. `mkdir artifacts` before attempt 1. Tee stdout/stderr to `artifacts/run.log`.

Child env for `house-run` (allowlist, plus the pipeline file, plus the literals above):

`DIGIKEY_URL`, `DIGISEARCH_URL`, `DIGIQUANT_DIGIKEY_API_KEY`, `OPENROUTER_API_KEY`, `CHEAPERINFERENCE_API_KEY`, `CHEAPERINFERENCE_API_BASE`, `CORE_POSTGRES_URI`, `LANGSMITH_API_KEY`, `R2_ACCOUNT_ID`, `R2_BUCKET`, `R2_ACCESS_KEY_ID`, `R2_SECRET_ACCESS_KEY`, `CORE_SUPABASE_URL`, `CORE_SUPABASE_SERVICE_KEY`.

`alias_supabase: true` so the child also gets `SUPABASE_URL` / `SUPABASE_SERVICE_ROLE_KEY` from the CORE pair (existing `build_child_env` behavior, #1090).

URL literals (not secrets): `DIGIKEY_URL=https://key.digithings.ai`, `DIGISEARCH_URL=https://search.digithings.ai`, `CHEAPERINFERENCE_API_BASE=https://api.cheaperinference.com/v1` unless the Worker secret of that name is non-empty. Put the URLs in `extra_env`. Put the keys in `env` so they come from `dataPlaneEnv`.

`build_child_env` already strips `RUNNER_AUTH_TOKEN` and `GH_ISSUE_TOKEN`. Keep that. `GITHUB_RUN_ID` is the runner UUID, not a token.

Publish `artifacts/` on success and on chain failure (`publish_always`), keys `pipeline-runs/house-run/<run_id>/…`. Do not publish on the SIGTERM path beyond `interrupted.json`. `success.json` is the Worker write on exit 0 only, not a file in `artifacts/`.

### Allocation-shadow follow-on

After house-run reaches `succeeded`, the DO enqueues command `allocation-shadow` on **this same class** with:

```json
{
  "artifact_prefix": "pipeline-runs/house-run/<house_run_id>/",
  "source_branch": "main"
}
```

`env` is `[]`. `alias_supabase` is false. `extra_env` is empty. `build_child_env` must not copy `OPENROUTER_API_KEY`, `CHEAPERINFERENCE_API_KEY`, `DIGIQUANT_DIGIKEY_API_KEY`, `LANGSMITH_API_KEY`, `CORE_POSTGRES_URI`, `CORE_SUPABASE_URL`, `CORE_SUPABASE_SERVICE_KEY`, `SUPABASE_URL`, `SUPABASE_SERVICE_ROLE_KEY`, `R2_SECRET_ACCESS_KEY`, or `GITHUB_RUN_ID` into that child. The parent `exec_job.py` may use the container's R2 env to download `shadow-allocation-*.json` from `artifact_prefix` into `/tmp/shadow-in/<run_id>/` **before** spawning the child. The child only sees local paths.

First argv is `check_allocation_shadow_isolation.py` with `--output /tmp/allocation-shadow-isolation-report.json` and `--artifact` for each downloaded file. Pass `--source-workflow` from the artifact JSON's own producer field when that field is present. Do not hardcode `Pipeline: digiquant research` to force the trust gate green. The trusted set stays `Pipeline: dashboard research`. A non-zero isolation result fails **this** command only. It does not delete `success.json` and does not flip the house run to failed.

Re-include and `COPY` only `.github/workflows/pipeline-digiquant-allocation-shadow.yml` so the checker's default workflow scan still sees the file. Do not change that workflow's `workflow_run` list.

Upload the isolation report to `pipeline-runs/allocation-shadow/<run_id>/allocation-shadow-isolation-report.json`.

---

## Secrets checklist (human — not this PR)

`printf '%s' "$VALUE" | env -u CLOUDFLARE_API_TOKEN npx wrangler secret put NAME` from `apps/digiquant-runner`. Never commit values. Never log them.

Already on the Worker (Phase 1/2): `RUNNER_AUTH_TOKEN`, `R2_ACCOUNT_ID`, `R2_BUCKET`, `R2_ACCESS_KEY_ID`, `R2_SECRET_ACCESS_KEY`, `CORE_POSTGRES_URI`, `CORE_SUPABASE_URL`, `CORE_SUPABASE_SERVICE_KEY`, `CLOUDFLARE_EMAIL_API_TOKEN`, `CLOUDFLARE_ACCOUNT_ID`, `NOTIFY_FROM`.

Add for Phase 3, and forward them in `dataPlaneEnv` (`apps/digiquant-runner/src/env.ts`):

| Name | Notes |
|---|---|
| `DIGIQUANT_DIGIKEY_API_KEY` | Scope `digisearch:query`. Rotation: `docs/ops/digiquant-digikey-service-key.md`. |
| `OPENROUTER_API_KEY` | House fallback upstream. |
| `CHEAPERINFERENCE_API_KEY` | House default upstream (`DIGI_HOUSE_UPSTREAM=cheaperinference` in the pipeline file). |
| `CHEAPERINFERENCE_API_BASE` | Only if production is not `https://api.cheaperinference.com/v1`. |
| `LANGSMITH_API_KEY` | Tracing. `LANGSMITH_PROJECT` is the literal `digiquant-baseline` in `extra_env`, not a secret. |

`DIGIKEY_URL` and `DIGISEARCH_URL` are literals in `extra_env`, not secrets.

Still absent: `FRED_API_KEY`, `GH_ISSUE_TOKEN`, broker credentials, Alpaca keys.

`allocation-shadow` does not get the new names in its command `env` list. Putting them on the Worker is not the same as handing them to that subprocess. `exec_job_test.py` is the proof.

R2 ledger reads from the Worker use an `[[r2_buckets]]` binding `ARCHIVE` on bucket `digithings-archive` (same bucket as `R2_BUCKET`). That is a binding, not a new vendor. Confirm the live bucket name before the first deploy. Container artifact upload keeps the existing boto3 path.

---

## GHA schedule / dispatch notes

- `pipeline-digiquant.yml` has no `schedule:` today. Do not add one. Add a header comment: the clock is digithings-cron → digiquant-runner; `repository_dispatch` type `digiquant-baseline` remains for a manual override; do not add `schedule:`.
- Do not delete the workflow. Do not delete `workflow_dispatch`.
- Cron stops sending `repository_dispatch` when the four jobs flip to `kind: "container"`. `GITHUB_OVERRIDE_JOBS=house-run-09,…` sends those ids down `workflow_dispatch` (`usesGithub` in `dispatch.ts`). That path sets `FORCE_RUN` true in the workflow (`github.event_name == 'workflow_dispatch'`), so the Actions skip script gets `--force`. Leave the override unset after the container proof. Log `github_override` at error, as today.
- `pipeline-digiquant-allocation-shadow.yml` stays `workflow_run` on `Pipeline: dashboard research`. The container follow-on does not depend on that filter matching. Do not "fix" the filter in this phase.
- Phase 4 is the one that removes remaining digiquant GHA compute. This phase does not.

---

## Files

| Path | Action |
|---|---|
| `docs/superpowers/plans/2026-09-30-digiquant-house-run-phase3.md` | This plan (this PR). |
| `docs/ops/digiquant-runner.md` | Pointer at this plan. Runbook section for kick / ledger / rollback lands with the implementation, after the behavior exists. |
| `apps/digiquant-runner/commands.json` | Add `house-run` and `allocation-shadow`. |
| `apps/digiquant-runner/src/commands.ts` | Optional `pipeline_env`, `export_args`, `checkpoint_run_id`, `publish_dir`, `publish_always`, `step_timeout_seconds` on the step type. |
| `apps/digiquant-runner/src/commands.test.ts` | Replace the "house-run is unknown" case. Assert argv, caps, empty shadow env, no `failure_issue`. |
| `apps/digiquant-runner/src/env.ts` | Forward the Phase 3 secret names from `dataPlaneEnv`. |
| `apps/digiquant-runner/src/index.ts` | Skip gate before `getContainer`. |
| `apps/digiquant-runner/src/runner-session.ts` | `skipped` is not used here (Worker returns it). Exclusive queue while `house-run` is locked. On house success, enqueue `allocation-shadow`. |
| `apps/digiquant-runner/src/runner.test.ts` | Unknown-command fixture becomes `not-a-command`. New cases: skip does not `startRun`; second command queues while house is locked; shadow env is not forwarded by the session (the Python test owns the env assertion). |
| `apps/digiquant-runner/container/exec_job.py` | Pipeline env, `GITHUB_RUN_ID`, directory publish, SIGTERM `interrupted.json`, stage R2 prefix for shadow. Preserve 409 and `_publish_bounded`. |
| `apps/digiquant-runner/container/exec_job_test.py` | New cases below. Existing busy-gate and publish-timeout tests stay green. |
| `apps/digiquant-runner/container/house_chain_step.py` | Create. Retry loop. No import of `digiquant.portfolio`. |
| `apps/digiquant-runner/container/house_chain_step_test.py` | Create. Argv and attempt counter only. |
| `apps/digiquant-runner/container/wake_stack.py` | Create. Stdlib HTTP. Always exit 0. |
| `apps/digiquant-runner/container/web_search_preflight.py` | Create. Six attempts, exit 1 if all fail. |
| `apps/digiquant-runner/wrangler.toml` | Comment update only in the code PR: Phase 3 secrets are now in scope. **No** second `[[containers]]`. **No** `instance_type` change. Add `[[r2_buckets]]` binding `ARCHIVE`. |
| `Dockerfile.digiquant-runner` | `COPY` the pipeline file, the shadow workflow file, the new container scripts, and only those workspace members the probe named. `uv sync` line is whatever the probe ladder stopped on. |
| `.dockerignore` | `!.github/digiquant-pipeline.yml` and `!.github/workflows/pipeline-digiquant-allocation-shadow.yml`. |
| `apps/digithings-cron/src/jobs.ts` | Four `rd(...)` house rows become `cj(...)`. |
| `apps/digithings-cron/src/index.ts` | Build house args. Strip scope / dry_run / resume unless `force`. |
| `apps/digithings-cron/src/dispatch.ts` | Treat `skipped` as success. |
| `apps/digithings-cron/src/jobs.test.ts` | House jobs are `container` / `house-run`. Crons unchanged. |
| `apps/digithings-cron/src/dispatch.test.ts` | Ordinary house body has `refresh_scope=none` and no GitHub fetch. |
| `digiquant/scripts/research/house_schedule_skip.py` | One-line comment at the top pointing at the R2 key. Behavior unchanged. |
| `.github/workflows/pipeline-digiquant.yml` | Header comment only. No `schedule:`. Titles in the report step stay byte-identical. |
| `apps/digithings-cron/README.md` | Replace the "house-run stays repository_dispatch" line when the flip lands. |

Do not edit `apps/digithings-stack-cloudflare/**`. Do not edit `digiquant/src/digiquant/portfolio/**` or `digiquant/src/digiquant/research/**`.

### Intended `commands.json` entries

`house-run` steps reference the wrapper scripts so the 2×100m loop is not a second copy of the chain. Flags inside `house_chain_step.py` are the workflow's flags.

```json
"house-run": {
  "timeout_seconds": 14400,
  "concurrency": "digiquant-pipeline",
  "code_ref": "main",
  "alias_supabase": true,
  "pipeline_env": ".github/digiquant-pipeline.yml",
  "checkpoint_run_id": true,
  "export_args": ["refresh_scope", "run_date", "dry_run", "resume_run_id"],
  "publish_dir": "artifacts",
  "publish_always": true,
  "extra_env": {
    "DIGIKEY_URL": "https://key.digithings.ai",
    "DIGISEARCH_URL": "https://search.digithings.ai",
    "CHEAPERINFERENCE_API_BASE": "https://api.cheaperinference.com/v1",
    "LANGSMITH_PROJECT": "digiquant-baseline",
    "DIGILLM_PROVIDER_MAX_ATTEMPTS": "2",
    "DIGILLM_EMPTY_RETRY_MAX": "1",
    "DIGILLM_MAX_CONCURRENT_CALLS": "8",
    "DIGIQUANT_SHADOW_ARTIFACT_MODE": "export",
    "DIGIQUANT_SHADOW_ARTIFACT_DIR": "artifacts"
  },
  "env": [
    "DIGIQUANT_DIGIKEY_API_KEY",
    "OPENROUTER_API_KEY",
    "CHEAPERINFERENCE_API_KEY",
    "CHEAPERINFERENCE_API_BASE",
    "CORE_POSTGRES_URI",
    "LANGSMITH_API_KEY",
    "R2_ACCOUNT_ID",
    "R2_BUCKET",
    "R2_ACCESS_KEY_ID",
    "R2_SECRET_ACCESS_KEY",
    "CORE_SUPABASE_URL",
    "CORE_SUPABASE_SERVICE_KEY"
  ],
  "steps": [
    {
      "argv": ["uv", "run", "--frozen", "--no-sync", "python", "-m", "digiquant", "prices", "fetch-macro", "--sources", "fedprob", "--manifest", "digiquant/src/digiquant/research/config/macro_series.yaml", "--dry-run"],
      "when_arg": "dry_run",
      "equals": "true",
      "continue_on_error": true
    },
    {
      "argv": ["uv", "run", "--frozen", "--no-sync", "python", "-m", "digiquant", "prices", "fetch-macro", "--sources", "fedprob", "--manifest", "digiquant/src/digiquant/research/config/macro_series.yaml", "--supabase"],
      "when_arg_empty": "dry_run",
      "continue_on_error": true
    },
    {
      "argv": ["uv", "run", "--frozen", "--no-sync", "python", "digiquant/scripts/research/validate-providers.py", "--skip-dry-run"],
      "step_timeout_seconds": 600
    },
    {
      "argv": ["uv", "run", "--frozen", "--no-sync", "python", "/opt/runner/wake_stack.py"],
      "continue_on_error": true
    },
    ["uv", "run", "--frozen", "--no-sync", "python", "/opt/runner/web_search_preflight.py"],
    {
      "argv": ["uv", "run", "--frozen", "--no-sync", "python", "/opt/runner/house_chain_step.py"],
      "step_timeout_seconds": 13800
    }
  ]
},
"allocation-shadow": {
  "timeout_seconds": 600,
  "concurrency": "digiquant-allocation-shadow",
  "code_ref": "main",
  "stage_r2_prefix_arg": "artifact_prefix",
  "env": [],
  "steps": [
    ["uv", "run", "--frozen", "--no-sync", "python", "digiquant/scripts/research/check_allocation_shadow_isolation.py", "--output", "/tmp/allocation-shadow-isolation-report.json"]
  ],
  "publish": ["/tmp/allocation-shadow-isolation-report.json"]
}
```

`exec_job.py` appends `--artifact <path>` for each staged file, and `--source-workflow` only when the artifact JSON already carries a producer name. The catalog step stays the checker first. `wake_stack.py` is `continue_on_error` as well as internally exit-0, so a missing script bug is the only hard failure from that slot before the preflight.

`CHEAPERINFERENCE_API_BASE` is in both `extra_env` and `env`. `build_child_env` applies `env` first and `extra_env` second today (`exec_job.py`). Swap that order for keys that are secrets-over-literals: a non-empty Worker value wins, the literal fills the gap. One test covers both.

---

## Tasks

Human tasks are marked **Human**. OpenCode / Coders tasks are mechanical and land only after this plan is accepted. Each code task keeps #4822 tests green.

### Task 0 — Human: measure disk

**Files:** none committed. Paste the inspect output into the implementation PR.

- [ ] **Step 1:** Run the [probe ladder](#probe-ladder) on a machine with Docker. Do not deploy.
- [ ] **Step 2:** Record `Size`, `free`, and the `uv sync` line that first printed `chain import ok`.
- [ ] **Step 3:** If free space is under 2 GiB or `Size` is not under 12 GiB, stop. Do not open an implementation PR that changes `instance_type`.

### Task 1 — Command catalog

**Files:**

- Modify: `apps/digiquant-runner/commands.json`
- Modify: `apps/digiquant-runner/src/commands.ts`
- Test: `apps/digiquant-runner/src/commands.test.ts`

**Interfaces:**

- Consumes: existing `CommandSpec` / `GatedStep`.
- Produces: commands `house-run` and `allocation-shadow` with the JSON above. `GatedStep.step_timeout_seconds?: number`. `CommandSpec` gains the optional fields named in the file table.

- [ ] **Step 1: Write the failing test**

Replace the unknown-command case that names `house-run`. Point the unknown assertion at `not-a-command`.

```ts
it("house-run matches the workflow caps and does not file issues", () => {
  const spec = assertKnownCommand("house-run", raw);
  expect(spec.timeout_seconds).toBe(14400);
  expect(spec.concurrency).toBe("digiquant-pipeline");
  expect(spec.extra_env?.DIGILLM_MAX_CONCURRENT_CALLS).toBe("8");
  expect(spec.extra_env?.DIGIQUANT_SHADOW_ARTIFACT_MODE).toBe("export");
  const flat = JSON.stringify(spec.steps);
  expect(flat).toContain("fetch-macro");
  expect(flat).toContain("fedprob");
  expect(flat).toContain("validate-providers.py");
  expect(flat).toContain("house_chain_step.py");
  expect(spec).not.toHaveProperty("failure_issue");
});

it("allocation-shadow allowlist is empty and the checker is first", () => {
  const spec = assertKnownCommand("allocation-shadow", raw);
  expect(spec.env).toEqual([]);
  expect(spec.alias_supabase).toBeFalsy();
  const first = spec.steps[0];
  const argv = Array.isArray(first) ? first : first.argv;
  expect(argv.join(" ")).toContain("check_allocation_shadow_isolation.py");
  expect(JSON.stringify(spec)).not.toContain("OPENROUTER");
  expect(JSON.stringify(spec)).not.toContain("CORE_SUPABASE");
});
```

- [ ] **Step 2:** `cd apps/digiquant-runner && npx vitest run src/commands.test.ts` — FAIL (`house-run` missing or still unknown).
- [ ] **Step 3:** Add the JSON and the type fields.
- [ ] **Step 4:** Re-run until PASS. `npm run test --workspace digiquant-runner` still passes, including the #4822 cases.
- [ ] **Step 5:** Commit `feat(digiquant): add house-run command catalog`.

### Task 2 — Chain argv wrapper

**Files:**

- Create: `apps/digiquant-runner/container/house_chain_step.py`
- Test: `apps/digiquant-runner/container/house_chain_step_test.py`

**Interfaces:**

- Consumes: env `RUN_DATE`, `REFRESH_SCOPE`, `DRY_RUN`, `RESUME_RUN_ID`, `GITHUB_RUN_ID` (set by `exec_job.py` in Task 3).
- Produces: `chain_argv(env: Mapping[str, str]) -> list[str]` and `run_attempts(env, spawn) -> int` with `MAX_OUTER_ATTEMPTS = 2`, `BACKOFF_SECONDS = (0, 300)`, `ATTEMPT_TIMEOUT_SECONDS = 6000`.

- [ ] **Step 1: Failing test** (`python apps/digiquant-runner/container/house_chain_step_test.py`)

```python
def test_chain_argv_daily_flags():
    argv = chain_argv({
        "RUN_DATE": "2026-09-30",
        "REFRESH_SCOPE": "none",
        "GITHUB_RUN_ID": "run-1",
    })
    assert argv == [
        "uv", "run", "--frozen", "--no-sync", "python", "-m",
        "digiquant.portfolio.chain",
        "--cadence", "daily",
        "--run-date", "2026-09-30",
        "--refresh-scope", "none",
    ]

def test_chain_argv_dry_run_and_resume():
    argv = chain_argv({
        "RUN_DATE": "2026-09-30",
        "REFRESH_SCOPE": "all",
        "DRY_RUN": "true",
        "RESUME_RUN_ID": "run-0",
    })
    assert "--dry-run" in argv
    assert argv[argv.index("--resume-run-id") + 1] == "run-0"

def test_second_attempt_sets_digiquant_attempt():
    seen: list[str] = []

    def spawn(argv: list[str], env: dict[str, str]) -> int:
        del argv
        seen.append(env["DIGIQUANT_ATTEMPT"])
        return 1 if len(seen) == 1 else 0

    code = run_attempts(
        {"RUN_DATE": "2026-09-30", "REFRESH_SCOPE": "none"},
        spawn,
        sleep=lambda _seconds: None,
    )
    assert code == 0
    assert seen == ["1", "2"]
```

The test substitutes `spawn`. It does not call `uv` or the chain.

- [ ] **Step 2:** Run the test. Expected: FAIL (`chain_argv` missing).
- [ ] **Step 3:** Implement the wrapper. `DIGIQUANT_ATTEMPT` is exported on the child for that attempt. Attempt 1 sleeps 0. Attempt 2 sleeps 300s only after attempt 1's non-zero. Kill the attempt process group at 6000s, then `SIGKILL` after 30s.
- [ ] **Step 4:** Test passes.
- [ ] **Step 5:** Commit `feat(digiquant): add house chain attempt wrapper`.

### Task 3 — exec_job extensions

**Files:**

- Modify: `apps/digiquant-runner/container/exec_job.py`
- Test: `apps/digiquant-runner/container/exec_job_test.py`
- Create: `wake_stack.py`, `web_search_preflight.py` (unit-test the attempt loops with a fake `urlopen` / fake healthcheck function; do not hit the network).

**Interfaces:**

- Consumes: Task 1 catalog fields, Task 2 `house_chain_step.py`.
- Produces: `load_pipeline_env(text: str) -> dict[str, str]`; child env includes pipeline keys and `GITHUB_RUN_ID` when `checkpoint_run_id` is set; `interrupted_body(run_id, run_date) -> dict`; directory publish keys; shadow staging does not leak into the child env.

- [ ] **Step 1: Failing tests** in `exec_job_test.py`

```python
def test_pipeline_env_parses_tier_and_checkpointer():
    text = "env:\n  DIGIQUANT_MODEL_TIER: \"cheap\"\n  DIGI_CHECKPOINTER: postgres\n"
    got = load_pipeline_env(text)
    assert got["DIGIQUANT_MODEL_TIER"] == "cheap"
    assert got["DIGI_CHECKPOINTER"] == "postgres"

def test_house_child_has_github_run_id_and_not_runner_token(tmp_path, monkeypatch):
    monkeypatch.setenv("RUNNER_AUTH_TOKEN", "sekret")
    monkeypatch.setenv("GH_ISSUE_TOKEN", "nope")
    env = build_child_env("house-run", run_id="run-abc")
    assert env["GITHUB_RUN_ID"] == "run-abc"
    assert "RUNNER_AUTH_TOKEN" not in env
    assert "GH_ISSUE_TOKEN" not in env

def test_shadow_child_has_no_prod_secrets(monkeypatch):
    for name in (
        "OPENROUTER_API_KEY", "CHEAPERINFERENCE_API_KEY",
        "DIGIQUANT_DIGIKEY_API_KEY", "LANGSMITH_API_KEY",
        "CORE_POSTGRES_URI", "CORE_SUPABASE_URL",
        "CORE_SUPABASE_SERVICE_KEY", "R2_SECRET_ACCESS_KEY",
    ):
        monkeypatch.setenv(name, "sekret")
    env = build_child_env("allocation-shadow", run_id="s1")
    for name in (
        "OPENROUTER_API_KEY", "CORE_SUPABASE_URL", "SUPABASE_URL",
        "LANGSMITH_API_KEY", "CORE_POSTGRES_URI", "R2_SECRET_ACCESS_KEY",
        "GITHUB_RUN_ID",
    ):
        assert name not in env

def test_interrupted_body_uses_runner_run_id():
    assert interrupted_body("run-abc", "2026-09-30") == {
        "resume_run_id": "run-abc",
        "run_date": "2026-09-30",
    }
```

Keep the existing tests that cover 409 `_running_command` and the 120s publish bound.

- [ ] **Step 2:** `python apps/digiquant-runner/container/exec_job_test.py` fails on the new names.
- [ ] **Step 3:** Implement. Directory upload lists files under `publish_dir` and uses `_publish_bounded`. SIGTERM calls the existing status write, then a best-effort upload of `interrupted.json` to `pipeline-runs/house-run/<run_date>/interrupted.json`. `when_arg_empty: dry_run` selects the `--supabase` fedprob step.
- [ ] **Step 4:** `exec_job_test.py` passes. `npm run test --workspace digiquant-runner` passes.
- [ ] **Step 5:** Commit `feat(digiquant): house-run child env, ledger hooks, shadow isolation`.

### Task 4 — Worker skip gate and exclusive queue

**Files:**

- Modify: `apps/digiquant-runner/src/index.ts`
- Modify: `apps/digiquant-runner/src/runner-session.ts`
- Modify: `apps/digiquant-runner/src/runner.ts` (no sleepAfter change)
- Test: `apps/digiquant-runner/src/runner.test.ts`

**Interfaces:**

- Consumes: R2 binding `ARCHIVE` with `head` / `put` / `get`. Fake it in tests.
- Produces: `202` `status: "skipped"` without `startRun` when `success.json` exists. `accept()` queues a different concurrency group while a run with `command === "house-run"` holds a lock. `promote` after house success enqueues one `allocation-shadow` whose args contain `artifact_prefix`. `Env.ARCHIVE.head(key)` / `.put(key, body)` / `.get(key)`. A `step_timeout_seconds` cap is `min(step_timeout_seconds, remaining job deadline)`.

- [ ] **Step 1: Failing tests**

```ts
it("skips house-run before start when today's success object exists", async () => {
  const { session, starts } = harness();
  const env = envFor(session, {
    archive: { "pipeline-runs/house-run/2026-09-30/success.json": "{\"run_id\":\"old\"}" },
  });
  const res = await worker.fetch(
    post(job({
      command: "house-run",
      concurrency: "digiquant-pipeline",
      args: { refresh_scope: "none", run_date: "2026-09-30" },
    })),
    env,
  );
  expect(res.status).toBe(202);
  expect(await res.json()).toMatchObject({ status: "skipped" });
  expect(starts).toHaveLength(0);
});

it("force bypasses the success object and starts", async () => {
  const { session, starts } = harness();
  const env = envFor(session, {
    archive: {
      "pipeline-runs/house-run/2026-09-30/success.json": "{\"run_id\":\"old\"}",
    },
  });
  const res = await worker.fetch(
    post(job({
      command: "house-run",
      concurrency: "digiquant-pipeline",
      args: { refresh_scope: "none", run_date: "2026-09-30", force: "true" },
      idempotency_key: "house-run-09:force",
    })),
    env,
  );
  expect(res.status).toBe(202);
  expect((await res.json()).status).toBe("accepted");
  expect(starts).toHaveLength(1);
});

it("queues prices while house-run is locked", async () => {
  const { session, starts } = harness();
  const env = envFor(session);
  const house = await worker.fetch(
    post(job({
      command: "house-run",
      job_id: "house-run-09",
      concurrency: "digiquant-pipeline",
      timeout_seconds: 14400,
      idempotency_key: "house-run-09:1",
      args: { refresh_scope: "none", run_date: "2026-09-30" },
    })),
    env,
  );
  expect(house.status).toBe(202);
  const prices = await worker.fetch(
    post(job({
      command: "market-data-refresh",
      concurrency: "market-data-refresh",
      idempotency_key: "market-data-refresh-morning:2",
    })),
    env,
  );
  expect(prices.status).toBe(202);
  expect((await prices.json()).status).toBe("accepted");
  expect(starts).toHaveLength(1);
});
```

Change the old unknown-command test to `command: "not-a-command"`.

- [ ] **Step 2:** Vitest FAIL.
- [ ] **Step 3:** Implement the skip in `index.ts` before `stub(env)`. Implement the queue rule in `accept` / `promote`. Write `success.json` from the DO when house-run transitions to `succeeded`. Missing `ARCHIVE` on a house-run POST returns 500 and does not `startRun`.
- [ ] **Step 4:** `npm run test --workspace digiquant-runner` PASS, including #4822 watchdog cases in `runner.test.ts`.
- [ ] **Step 5:** Commit `feat(digiquant): skip a finished house-run and queue other cadence`.

### Task 5 — Cron flip

**Files:**

- Modify: `apps/digithings-cron/src/jobs.ts`
- Modify: `apps/digithings-cron/src/index.ts`
- Modify: `apps/digithings-cron/src/dispatch.ts`
- Test: `jobs.test.ts`, `dispatch.test.ts`, `index.test.ts`

**Interfaces:**

- Consumes: runner `skipped` status.
- Produces: four container jobs. `houseArgs(force, bodyArgs, now) -> Record<string, string>`.

- [ ] **Step 1: Failing tests**

```ts
expect(JOBS.find((job) => job.id === "house-run-09")).toMatchObject({
  kind: "container",
  command: "house-run",
  concurrency: "digiquant-pipeline",
  timeoutSeconds: 14400,
  cron: "17 9 * * *",
});

it("ordinary house dispatch sends refresh_scope none and does not call GitHub", async () => {
  // args.refresh_scope === "none"
  // args.run_date matches UTC day of scheduledTime
  // args has no dry_run and no resume_run_id
  // global fetch not called
});

it("kick without force strips refresh_scope all", async () => { /* sent as none */ });
it("kick with force keeps refresh_scope all and dry_run", async () => { /* and args.force === "true" */ });
it("skipped container status is ok", async () => { /* isContainerSuccess / dispatch result ok */ });
```

- [ ] **Step 2:** `npm run test --workspace digithings-cron` FAIL.
- [ ] **Step 3:** Replace the four `rd(...)` calls with `cj(...)`. Build args in the cron Worker. Extend `isContainerSuccess` with `status === "skipped"`.
- [ ] **Step 4:** Tests PASS. `uniqueEnabledCrons()` still matches `wrangler.toml` (the four crons already exist).
- [ ] **Step 5:** Commit `feat(digiquant): point house-run cron at digiquant-runner`.

Do not set `GITHUB_OVERRIDE_JOBS` in `wrangler.toml` (it stays `""`).

### Task 6 — Image slim, dockerignore, workflow comment

**Files:** `Dockerfile.digiquant-runner`, `.dockerignore`, `.github/workflows/pipeline-digiquant.yml` header, `digiquant/scripts/research/house_schedule_skip.py` comment, `docs/ops/digiquant-runner.md` runbook, `apps/digithings-cron/README.md`, `apps/digiquant-runner/wrangler.toml` comment + `ARCHIVE` binding.

- [ ] **Step 1:** Apply the sync line and `COPY` set from Task 0. Refuse the edit if Task 0's numbers are absent from the PR body.
- [ ] **Step 2:** `wrangler.toml` still has one `[[containers]]` and `instance_type = "standard-2"`. A vitest or a tiny node assert in `commands.test.ts` can read the file and lock that.
- [ ] **Step 3:** Header comment on `pipeline-digiquant.yml`. One-line comment on `house_schedule_skip.py`:

```python
# Container ledger (Phase 3): pipeline-runs/house-run/<YYYY-MM-DD>/success.json
# on digiquant-runner. This script remains the GitHub Actions gate.
```

- [ ] **Step 4:** Local image check, no prod credentials:

```bash
docker build -f Dockerfile.digiquant-runner -t digiquant-runner:house .
docker run --rm digiquant-runner:house python -c "import digiquant.portfolio.chain; print('chain import ok')"
docker run --rm digiquant-runner:house python /opt/runner/house_chain_step.py --help
```

`--help` on the wrapper should print the attempt caps and exit 0 without calling the chain. If you did not add `--help`, run `house_chain_step_test.py` inside the image instead.

- [ ] **Step 5:** Commit `feat(digiquant): bake the house-run image on the standard-2 class`.

### Task 7 — Human: secrets, deploy, proof

Not part of the mechanical PR until Tasks 0–6 are green and the image numbers are in the PR.

- [ ] Put the [secrets](#secrets-checklist-human--not-this-pr). Confirm `ARCHIVE` is `digithings-archive`.
- [ ] `npx wrangler deploy` from `apps/digiquant-runner`, then from `apps/digithings-cron`.
- [ ] Forced dry-run, no Actions run:

```bash
curl -sS -X POST "$CRON_ORIGIN/kick" \
  -H "Authorization: Bearer $CRON_KICK_SECRET" \
  -H "content-type: application/json" \
  -d '{"cron":"17 9 * * *","force":true,"args":{"dry_run":"true","refresh_scope":"none"}}'
```

Expect `ok: true` and a `run_id`. Poll `GET /runs/:run_id` on digithings-cron until `succeeded` or a real `failed`. Workers Logs for that kick contain no `repository_dispatch` and no `actions/workflows/pipeline-digiquant.yml`. The Actions tab shows no new run.

- [ ] Second kick the same UTC date **without** `force` returns `skipped` and does not cold-start (no new container boot in Workers Logs).
- [ ] A real daily run (no `dry_run`) writes `pipeline-runs/house-run/<UTC date>/success.json` and `pipeline-runs/house-run/<run_id>/` artifacts. digikey and digisearch `/healthz` were both true in the log before `web-search healthcheck` (the wake script prints that line).
- [ ] After success, one `allocation-shadow` run exists. Its log tail does not contain `OPENROUTER_API_KEY` or `CORE_SUPABASE`. The isolation script is the first command line.
- [ ] `GITHUB_OVERRIDE_JOBS` is empty after the proof.
- [ ] Confirm the instance returns to idle: after the queue drains, Workers Logs show the container stop within a few minutes (`sleepAfter` 2m), not a resident fleet.

---

## Acceptance checklist

Adapted from epic Phase 3. Sizing lines follow the Chris lock, not the epic's `standard-4` class.

- [ ] `npm run test --workspace digiquant-runner` and `npm run test --workspace digithings-cron` pass.
- [ ] `python apps/digiquant-runner/container/exec_job_test.py` and `house_chain_step_test.py` pass.
- [ ] `wrangler.toml` has one container class, `DigiQuantRunnerContainer`, `instance_type = "standard-2"`, `max_instances = 1`.
- [ ] Image probe output is in the implementation PR, and free space on `/` is at least 2 GiB.
- [ ] A forced dry-run kick finishes with no GitHub Actions run.
- [ ] A second same-day kick without `force` does not start the chain (`status: skipped`, no cold start).
- [ ] A real daily run writes `pipeline-runs/house-run/<YYYY-MM-DD>/success.json`.
- [ ] Wake log shows digikey and digisearch `/healthz` both true before the web-search preflight on that real run.
- [ ] No `workflow_dispatch` and no `repository_dispatch` for `digiquant-baseline` from the cron tick.
- [ ] `allocation-shadow` runs on the same class after success, checker first, child env empty of prod secrets.
- [ ] `pipeline-digiquant-allocation-shadow.yml` `workflow_run` workflows list is still only `Pipeline: dashboard research`.
- [ ] `FRED_API_KEY` and `GH_ISSUE_TOKEN` are unset on the runner.
- [ ] #4822 tests still cover 409 same-command busy, 120s publish bound, and lock held while status is `running`.
- [ ] After the queue drains, the instance is reaped (`sleepAfter` 2m). `max_instances` is still 1.
- [ ] `GITHUB_OVERRIDE_JOBS` is empty in production after the proof.
- [ ] No new public DNS name.

---

## Risks

| Risk | Why it matters | What to do |
|---|---|---|
| SIGTERM during a 240 minute run | Cloudflare may move the host: SIGTERM, 15 minute grace, then SIGKILL. There is no promise of four quiet hours. | `_on_sigterm` writes `interrupted.json` with the runner `run_id`. Later ticks pass `--resume-run-id`. Heartbeat keeps the instance up only while the lock is held. Do not invent a second resume format. `resolve_run_id` stays as it is; `GITHUB_RUN_ID` on the child is how the chain already names the thread. |
| Disk on 12 GB | `--all-packages --all-extras` plus nautilus can exceed `standard-2`. Phase 2 already fits nautilus (wheel 182608916 bytes) on this class. The chain's extra members are the unknown. | Probe ladder. Stop if the cutover bar fails. |
| Last-resort upsize or second class | A second image or `standard-3` / `standard-4` would bill more and add a fleet. Chris rejected both. | Do not implement. If the probe cannot fit, the implementation PR stops and asks. Shipping a second `[[containers]]` block is a failed Phase 3. |
| LLM spend | A skip miss runs the chain twice in one UTC day. `force` plus `refresh_scope=all` is a full rewrite. | Skip gate before cold start. Ordinary ticks send `refresh_scope=none`. Missing ledger fails closed for house-run only. `DIGILLM_*` caps match the workflow (provider attempts 2, empty retry 1, 8 in flight). |
| House blocks prices | Exclusive queue (recommended) delays price ticks until the chain exits. Overlap (today's `MAX_INFLIGHT`) can OOM the 6 GiB box. | See [open question](#open-questions). Either way, one instance, then reap. Do not start a second instance to "save" prices. |
| Queue keeps the instance awake | `hasActiveWork` includes the queue, so serialized prices extend the bill past the chain. | That is still one instance. It reaps 2 minutes after the queue is empty. Do not raise idle `sleepAfter` to hide the cold start. |
| Cold start | The tick after reap pays container boot (seconds to a couple of minutes, not a `uv sync`). | Accepted. `/healthz` `git_sha` is the image pin. Redeploy the runner after promoting pipeline code to `main`. |
| digikey wake (#4546) | digisearch can answer before digikey serves JWKS. | 12-attempt wake, then 6-attempt `web-search healthcheck`. Do not start the chain earlier. Wake failure is non-fatal; preflight failure is fatal. |
| `allocation-shadow` trust name | The checker will keep failing closed while artifacts name `Pipeline: digiquant research`. | Do not repair it here. House `success.json` is already written. The follow-on failure is its own run. |
| Directory publish vs 120s bound | A huge `artifacts/` tree could hit `PUBLISH_TIMEOUT_SECONDS` and fail an otherwise good run. | Keep the bound (#4822). House artifacts are the log plus shadow JSON. If a proof hits the timeout, raise only that command's bound in a follow-up. Do not remove the bound. |
| `GITHUB_OVERRIDE_JOBS` left on | Burns Actions minutes and, for these jobs, `workflow_dispatch` forces the Actions skip script. | Error log. Acceptance requires the var empty. |
| Secrets in the shadow child | `dataPlaneEnv` puts house keys on the container process. A sloppy `os.environ` copy would hand them to the checker. | `env: []` plus the `exec_job_test.py` assertion. Parent stages R2 objects; the child sees paths. |
| Failure-issue titles | Dedup on the GHA override path is byte-identity of `digiquant-daily-failure` and `digiquant-daily-cancelled`. | Do not edit those title strings. Do not add `GH_ISSUE_TOKEN` to "keep dedup working" from the container. The container does not file the issue. |
| Double clock | Re-adding `schedule:` or leaving the cron on `repository_dispatch` while the container also runs. | Flip `kind` and leave the workflow without `schedule:`. |
| #4822 regression | Releasing the house lock while `/status` is `running`, or ignoring 409, starts two writers. | Keep `pollLock` and `_running_command`. New tests must not delete those cases. |

---

## Open questions

Instance type is **not** open. It is `standard-2` on `DigiQuantRunnerContainer`.

1. **Does house-run serialize the other cadence?** Recommended default in this plan: yes — queue prices, market-data, tearsheets, on-chain, metrics, and the execution probe while the `house-run` lock is held; promote them after it finishes; still one instance; reap after the queue drains. The alternative is today's `MAX_INFLIGHT = 2`, which lets one other command share the 1 vCPU / 6 GiB box with the chain. Chris / One should pick before Task 4 is implemented. Task 4's test is written for the recommended default.

No other product question blocks the catalog, the wrapper, or the image probe.
