# digiquant Phase 4 GHA cutover Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Move the last digiquant production compute off GitHub Actions runners onto the existing digiquant-runner, and replace the two prod smokes with Worker `fetch` inside digithings-cron, leaving each workflow file as a manual override.

**Architecture:** One Worker, one Durable Object id (`runner-v1`), one container class (`DigiQuantRunnerContainer`), one image, `instance_type = "standard-2"`, `max_instances = 1`, idle `sleepAfter = "2m"`. Checkpoint archive becomes one more command on that class. Site and stack smokes never start the container. digithings-cron stays the only clock. No Queues. The Durable Object already serializes concurrency groups.

**Tech Stack:** Cloudflare Workers + Containers (`@cloudflare/containers`), wrangler, Python 3.12, uv, Vitest, the existing stdlib `exec_job.py`. Account id stays `ae2ea3eb4ce5f7cc9bec1478f6e60e15`.

**Status:** plan only. Written 2026-10-01 against `origin/develop` @ `5ab8275a8` (squash of #4894, the Phase 3 image bake). This document does not flip cron, delete a `schedule:` key, put secrets, or deploy. Epic [#4761](https://github.com/digithings-ai/digithings/issues/4761) stays open. Implementation PRs say `Part of #4761` and do not close the epic.

---

## Prerequisite — Phase 3 Task 7 (out of scope)

Phase 3 house-run code is on `develop`: CHR-A runner path (#4891) and CHR-C image bake (#4894). CHR-B cron flip is [#4897](https://github.com/digithings-ai/digithings/pull/4897) (in flight on this date). **Phase 3 Task 7** — put house secrets, deploy the runner and the cron Worker, prove a dry-run kick with no Actions run — is One-owned after CHR-B lands. It is a prerequisite for the Phase 4 clock flip. It is not a Phase 4 task. Do not repeat it, do not move its secrets checklist into this plan, and do not treat a red house proof as a Phase 4 bug.

On this SHA, `apps/digithings-cron/src/jobs.ts` still has `house-run-09`…`12` as `repository_dispatch`. After #4897 merges they are `kind: "container"`. Phase 4 does not edit those four rows. Rebase onto `develop` after #4897. A rebase that turns them back into `repository_dispatch` is a failed Phase 4.

Catalog and image PRs (CHR-A, CHR-C) may merge before Task 7 because `deploy-digiquant-runner.yml` does not deploy on push to `develop` (it is `main` path-filter plus `workflow_dispatch` with `environment: production`). The image deploy and the cron-flip PR wait until Task 7 has finished, so two production runner deploys do not race.

---

## Chris lock — one class, standard-2

Locked for this plan. An implementation PR that violates it is out of scope.

| Decision | Locked value |
|---|---|
| Container class | `DigiQuantRunnerContainer` only. `wrangler.toml` keeps a single `[[containers]]` entry. |
| Instance type | `instance_type = "standard-2"` (1 vCPU, 6 GiB memory, 12 GB disk). |
| Image | The existing `Dockerfile.digiquant-runner`. Add two script `COPY` lines. Do not change the `uv sync` line. |
| Instances | `max_instances = 1`. Durable Object id stays `runner-v1`. |
| Idle | `sleepAfter = "2m"` when the ledger has no lock and no queue. |
| Smokes | Worker `fetch` inside digithings-cron. Zero container seconds. |
| Second class / standard-3 / standard-4 | Rejected. Recorded under [Risks](#risks) as a doomed escape hatch this phase does not implement. |

The epic's Phase 3 paragraph names a third class `DigiQuantHouseContainer` at `standard-4`. The [Phase 3 plan](2026-09-30-digiquant-house-run-phase3.md) already rejected that sizing. Phase 4 inherits the rejection. Checkpoint archive is a Postgres + R2 job on the research extra the image already has. It is not a reason to upsize.

---

## Cost

Cost-effectiveness is the architecture. The bill is memory-time of one `standard-2` while it is awake, plus a 2 minute idle tail. Prices, market-data, tearsheets, on-chain, metrics, the execution probe, house-run, and checkpoint archive share that one instance. A larger `instance_type` would raise the rate for every one of those jobs. A second class would be a second image to build, pin, and roll back, and a second instance that can stay awake beside the first.

| Choice | What it costs | Phase 4 decision |
|---|---|---|
| Reuse `DigiQuantRunnerContainer`, `standard-2`, `max_instances = 1` | Checkpoint archive holds the one instance for at most 3600s, then the existing queue drains, then the `2m` reap. Smokes add Workers subrequest time only. | This is the design. |
| Idle `sleepAfter = "2m"` | After the last lock drops and the queue is empty, the next `onActivityExpired` reaps. The `30m` window is the heartbeat renewal while work is held, not an extra half hour after exit. | Leave it. |
| Queues | A second product, a consumer, and something to keep awake. The Durable Object already serializes concurrency groups and queues a third request in storage. | Do not add Cloudflare Queues. |
| Always-on fleet | `max_instances` above 1, a raised idle `sleepAfter`, or a cron ping of `/healthz` bills the idle window on every price tick. | Do not build one. Cold start on the next tick is accepted. |
| Compose inside the container | `smoke-stack.yml` runs `docker compose up`. That needs a Docker daemon and the full stack image set. | Prod cadence is three public `/healthz` fetches. Compose stays a manual `workflow_dispatch` for a human with Docker. |
| Second class or `standard-3` / `standard-4` | Raises the memory-time rate and adds a fleet. Chris rejected both on the Phase 3 plan. | Do not implement. See [Risks](#risks). |

House-candidate image size on this SHA is 1344917045 bytes (~1.253 GiB), recorded in the Dockerfile header. Two script copies do not change the sync line. The 12 GB disk bar stays the one from Phase 3: if a later `docker image inspect` `Size` is not under 12 GiB, stop and ask. Do not change `instance_type` inside the implementation PR.

---

## Global constraints

- Digi product names stay lowercase in prose, docs, commits, and PR text.
- Polars only. Pydantic v2. Do not add pandas.
- Do not edit live-trading paths or `digiquant/brokers/`.
- Do not put broker credentials, Alpaca keys, or `--execute` on the runner.
- Do not edit `digiquant.ops.checkpoint_archive` or `scripts/digiquant_archive_checkpoints.py` / `scripts/digiquant_checkpoint_size_gate.py` behavior. Call them.
- Code pin stays released `main` baked into the image. Hot path stays `uv run --frozen --no-sync`. Do not `uv sync` on a tick.
- `GITHUB_OVERRIDE_JOBS` empty means migrated jobs never call `api.github.com`.
- Do not add a `schedule:` key to any workflow. Phase 4 deletes the one remaining digiquant `schedule:` (checkpoint archive) in the cron-flip PR.
- No public hostname. `workers_dev = false` on the runner. No `[[routes]]`.
- No `FRED_API_KEY`. No `GH_ISSUE_TOKEN`. The runner does not file GitHub issues. The smoke probes do not file GitHub issues either. Workers Logs are the prod signal. The manual workflow files still contain their issue steps for a human `workflow_dispatch`.
- #4822 stays in force: same-command `POST /run` returns 409 while that command's status is `running`; artifact publish is bounded by `PUBLISH_TIMEOUT_SECONDS = 120`; the DO keeps the concurrency lock while `/status` is still non-terminal.
- `deploy-digithings-cron.yml` deploys on push to `develop` when `apps/digithings-cron/**` changes. A cron-flip PR merges onto a live clock. See [CHR split](#chr-split-one-assigns-these).

---

## Non-goals

- Phase 3 Task 7 (house secrets, house deploy, house dry-run proof). Prerequisite only.
- Phase 5: `pipeline-continuous-improvement.yml`, `pipeline-provider-review.yml`, `pipeline-maintenance.yml`, `agent-pr-finalizer.yml`, `agent-backlog-snapshot.yml`, `project-enforce-assignment.yml`, `refresh-repo-activity.yml`, `ci-pr-hygiene.yml`, `security-pip-audit.yml`, `security-npm-audit.yml`, `token-canary.yml`, and every `twelve-x-*` job. They stay `workflow_dispatch` from digithings-cron. twelve-x stays on GHA dispatch. If minutes still hurt after Phase 4, open a separate issue.
- OpenWiki's `schedule:` (`openwiki-update.yml`). Not digiquant cadence.
- CI, type-check, docs, PR hygiene, security audits, deploy build checks. They stay on GHA.
- Rewriting checkpoint archive, size-gate relief math, or VACUUM. `docs/ops/checkpoint-archive-vacuum.md` stays true: the size gate is not a trailing step of the archive. The 13:30 job captures the pre snapshot only. Relief is still an operator compare after the 05:50 pg_cron vacuum.
- Repairing the allocation-shadow `workflow_run` name filter. `.github/workflows/pipeline-digiquant-allocation-shadow.yml` listens for `Pipeline: dashboard research`. The live house workflow name is `Pipeline: digiquant research`. Leave that mismatch. Phase 3 non-goal. Do not edit `TRUSTED_SOURCE_WORKFLOWS` in `digiquant/scripts/research/check_allocation_shadow_isolation.py`.
- `smoke-langsmith.yml`. It is `workflow_dispatch` only and it is not in `jobs.ts`. It is not an enabled prod clock. Leave it manual. Do not add a cron, a container command, or `LANGSMITH_API_KEY` usage for it.
- Deleting pipeline YAML files. They stay the manual override through one clean week after cutover. A follow-up may delete them. This phase does not.
- A second container class, `standard-3`, `standard-4`, Queues, or `max_instances` above 1.
- Filing `[site-smoke]` GitHub issues from the Worker.

---

## Current state (verified on `5ab8275a8`)

| Surface | What is true today |
|---|---|
| Class | `apps/digiquant-runner/wrangler.toml` — one `[[containers]]`, `class_name = "DigiQuantRunnerContainer"`, `instance_type = "standard-2"`, `max_instances = 1`. |
| Image | `Dockerfile.digiquant-runner` — `uv sync --frozen --package digiquant --extra prices --extra research --extra nautilus`, then `uv sync --frozen --inexact --package digigraph --extra checkpoint-postgres`. House-candidate Size=1344917045. Copies the refresh, backfill, and execution-cron scripts. Does **not** copy `scripts/digiquant_archive_checkpoints.py` or `scripts/digiquant_checkpoint_size_gate.py`. Root `.dockerignore` ignores `scripts/` except the re-includes already listed. |
| Catalog | `apps/digiquant-runner/commands.json` has market-data, prices, onchain, execution, research-metrics, tearsheets, `house-run`, `allocation-shadow`. No `checkpoint-archive`. |
| Cron | `apps/digithings-cron/src/jobs.ts` — prices, market-data, tearsheets, onchain, metrics, execution probe are `kind: "container"`. House-run is still `repository_dispatch` until #4897. `smoke-stack` (`27 7 * * *`) and `smoke-site` (`17 6 * * *`) are `workflow_dispatch`. No `checkpoint-archive` job. `wrangler.toml` `[triggers].crons` has no `30 13 * * *`. |
| Checkpoint workflow | `.github/workflows/pipeline-checkpoint-archive.yml` name `Pipeline: checkpoint archive`. `schedule: cron: "30 13 * * *"`. `workflow_dispatch`. Concurrency `checkpoint-archive`, `cancel-in-progress: false`. `timeout-minutes: 60`. Steps: advisory `scripts/digiquant_checkpoint_size_gate.py --snapshot-out /tmp/checkpoint-size-pre.json` (`continue-on-error: true`), then `scripts/digiquant_archive_checkpoints.py --retain-days 1 --manifest-out /tmp/checkpoint-archive-manifests.json`. Artifacts via `actions/upload-artifact` (manifest retention 90 days; snapshot `if-no-files-found: ignore`). |
| Archive CLI | `checkpoint_archive.main` supports `--dry-run` (list threads, write nothing, return 0 before `--manifest-out`). Missing Supabase / R2 / `CORE_POSTGRES_URI` returns 2 on the live path. The workflow does not pass `--dry-run`. |
| Size gate | `--snapshot-out` is read-only and returns 0 after writing. Missing `CORE_POSTGRES_URI` returns 0 without writing (fail-open, no `--strict`). A missing file must not fail publish. |
| Secrets already on the runner | `RUNNER_AUTH_TOKEN`, `R2_*`, `CORE_POSTGRES_URI`, `CORE_SUPABASE_URL`, `CORE_SUPABASE_SERVICE_KEY`. Checkpoint archive needs only those. No new secret names. |
| Site smoke | `.github/workflows/smoke-site.yml` is `workflow_dispatch` only (schedule removed in #3579). Cron still starts `ubuntu-latest`. Probes and freshness jobs are listed under [Smokes](#smokes). Failure steps call `gh issue create`. |
| Stack smoke | `.github/workflows/smoke-stack.yml` is `workflow_dispatch` only. The job runs `docker compose up -d --wait` for digikey, digigraph, digiquant, digisearch, digismith, then curls localhost `:8005` `:8000` `:8001` `:8002` `:8003`. |
| LangSmith smoke | `.github/workflows/smoke-langsmith.yml` is `workflow_dispatch` only. Not in `jobs.ts`. |
| Deploy | `deploy-digithings-cron.yml` deploys on push to `develop` for `apps/digithings-cron/**`. `deploy-digiquant-runner.yml` deploys on push to `main` (path-filtered) or `workflow_dispatch`, `environment: production`. |
| Pin test | `tests/scripts/test_checkpoint_archive_workflow.py::test_schedule_and_dispatch` asserts `"30 13 * * *"` is in `on.schedule`. |

---

## CHR split (One assigns these)

Each row is one assignable slice. Prod behavior changes only when the stated PR merges or a human deploys.

| ID | Slice | PR | Depends on | What "done" means |
|---|---|---|---|---|
| CHR-A | Runner command wiring | Own PR. `commands.json`, `exec_job.py` `publish_if_present`, tests. | Plan accepted. Rebase after #4897 if the branch touches cron (it should not). | `checkpoint-archive` is a known command. No cron edit. No workflow edit. No Dockerfile edit. |
| CHR-C | Image bake | Own PR. Two `COPY` lines, two `.dockerignore` re-includes, Dockerfile header note. | CHR-A's `commands.json` is the one the image copies. | `python -c "import digiquant.ops.checkpoint_archive"` works in the image. `uv sync` line unchanged. `instance_type` unchanged. Does not deploy (develop push does not deploy the runner). |
| CHR-E | Smokes | Own PR. New `kind: "probe"` in digithings-cron. `smoke-site` and `smoke-stack` stop calling GitHub. | #4897 merged, so `jobs.ts` / `dispatch.ts` are not edited in parallel with the house flip. | Next `17 6 * * *` and `27 7 * * *` ticks do not start `ubuntu-latest`. No container boot. No new cron expression. Merging deploys digithings-cron. |
| CHR-D | Workflow schedule delete | A commit inside the CHR-B PR. Not its own merge. | The pytest pin and the YAML edit land with the cron row. | `pipeline-checkpoint-archive.yml` has `workflow_dispatch` and no `schedule:`. |
| CHR-B | Cron flip | Own PR, and it contains the CHR-D commit. `jobs.ts` + `wrangler.toml` cron `30 13 * * *`. | Phase 3 Task 7 done. CHR-A and CHR-C merged. Human has deployed that image (`workflow_dispatch` of `deploy-digiquant-runner.yml` or workstation `wrangler deploy`) and `/healthz` `git_sha` matches it. | Merging deploys digithings-cron (new trigger) and removes the GHA schedule in the same commit. |

Do not merge a PR that only deletes the checkpoint `schedule:`. Until the cron trigger exists, that is a day with no archive. Do not merge CHR-B while the workflow on `develop` still has `schedule:`. `deploy-digithings-cron.yml` would start the container at 13:30 and GitHub would also fire. One commit, one PR, both halves.

CHR-E may merge before CHR-B. It does not add a cron expression and it does not need the checkpoint image. It does deploy the cron Worker on merge, so it waits for #4897 to land first.

---

## Checkpoint archive

### Cron contract

New job `checkpoint-archive`, cron `30 13 * * *` (not in `wrangler.toml` today). `kind: "container"`, `command: "checkpoint-archive"`, `concurrency: "checkpoint-archive"`, `timeoutSeconds: 3600`. Keep `workflow: "pipeline-checkpoint-archive.yml"` and `ref: "develop"` so `GITHUB_OVERRIDE_JOBS=checkpoint-archive` can still `workflow_dispatch` that file.

Ordinary ticks send `args: {}`. Only `POST /kick` with `"force": true` may set `dry_run` to `"true"`. Any other caller has `dry_run` stripped. Scheduled ticks never set `dry_run`. There is no ET open gate.

`30 13 * * *` stays 30 minutes after `market-data-refresh-morning` (`0 13 * * *`) and after the house window (`17 9`–`17 12`). `--retain-days 1` still leaves the just-finished house thread. Do not move the cron.

Overlap with a market-data job that is still inside its 1800s budget uses the existing `MAX_INFLIGHT = 2`. Do not raise `max_instances`. Do not extend the Phase 3 house exclusive queue to this command. House-run is not in flight at 13:30 on a normal day.

### Steps, in order

Copied from `.github/workflows/pipeline-checkpoint-archive.yml`. Flags stay identical.

1. `uv run --frozen --no-sync python scripts/digiquant_checkpoint_size_gate.py --snapshot-out /tmp/checkpoint-size-pre.json` with `continue_on_error: true`. Advisory. A non-zero exit does not fail the job.
2. Live archive, when `dry_run` is absent:
   `uv run --frozen --no-sync python scripts/digiquant_archive_checkpoints.py --retain-days 1 --manifest-out /tmp/checkpoint-archive-manifests.json`
3. Dry-run archive, when `dry_run` equals `"true"`: the same argv plus `--dry-run`.

Child env (already on the Worker; `alias_supabase: true` so the child also gets `SUPABASE_URL` / `SUPABASE_SERVICE_ROLE_KEY`):

`CORE_SUPABASE_URL`, `CORE_SUPABASE_SERVICE_KEY`, `R2_ACCOUNT_ID`, `R2_BUCKET`, `R2_ACCESS_KEY_ID`, `R2_SECRET_ACCESS_KEY`, `CORE_POSTGRES_URI`.

No `OPENROUTER_API_KEY`, no `LANGSMITH_API_KEY`, no `GH_ISSUE_TOKEN`, no `FRED_API_KEY`, no `GITHUB_RUN_ID`.

### Publish

`exec_job.py` today raises `publish file missing` when a `publish` path is absent. Dry-run returns before `--manifest-out` is written. The size gate writes nothing when `CORE_POSTGRES_URI` is empty. Both paths are optional.

Add `publish_if_present: string[]` on the command spec. `_publish` skips a path that is not a file. It still uploads a file that exists, under `pipeline-runs/checkpoint-archive/<run_id>/<filename>`, through the existing boto3 path and `_publish_bounded` (120s). A required `publish` list stays strict for every other command.

Keys:

| Key | When it exists |
|---|---|
| `pipeline-runs/checkpoint-archive/<run_id>/checkpoint-archive-manifests.json` | Live run exited 0. |
| `pipeline-runs/checkpoint-archive/<run_id>/checkpoint-size-pre.json` | The advisory snapshot wrote the file. |

Do not upload GitHub Actions artifacts from the container path. The override workflow keeps `actions/upload-artifact` for a human dispatch.

### Intended `commands.json` entry

```json
"checkpoint-archive": {
  "timeout_seconds": 3600,
  "concurrency": "checkpoint-archive",
  "code_ref": "main",
  "alias_supabase": true,
  "env": [
    "CORE_SUPABASE_URL",
    "CORE_SUPABASE_SERVICE_KEY",
    "R2_ACCOUNT_ID",
    "R2_BUCKET",
    "R2_ACCESS_KEY_ID",
    "R2_SECRET_ACCESS_KEY",
    "CORE_POSTGRES_URI"
  ],
  "steps": [
    {
      "argv": ["uv", "run", "--frozen", "--no-sync", "python", "scripts/digiquant_checkpoint_size_gate.py", "--snapshot-out", "/tmp/checkpoint-size-pre.json"],
      "continue_on_error": true
    },
    {
      "argv": ["uv", "run", "--frozen", "--no-sync", "python", "scripts/digiquant_archive_checkpoints.py", "--retain-days", "1", "--manifest-out", "/tmp/checkpoint-archive-manifests.json", "--dry-run"],
      "when_arg": "dry_run",
      "equals": "true"
    },
    {
      "argv": ["uv", "run", "--frozen", "--no-sync", "python", "scripts/digiquant_archive_checkpoints.py", "--retain-days", "1", "--manifest-out", "/tmp/checkpoint-archive-manifests.json"],
      "when_arg_empty": "dry_run"
    }
  ],
  "publish_if_present": [
    "/tmp/checkpoint-archive-manifests.json",
    "/tmp/checkpoint-size-pre.json"
  ]
}
```

---

## Smokes

New job kind `"probe"`. `dispatch` runs it inside digithings-cron. It does not call `env.RUNNER`. It does not call `api.github.com` unless the job id is listed in `GITHUB_OVERRIDE_JOBS` (same rule as `container`, and the same `github_override` error log). `DRY_RUN=1` logs the URL list and returns ok.

A failed probe throws. The cron invocation is an error in Workers Logs. Do not `gh issue create`. Do not add `GH_ISSUE_TOKEN`. The workflow files keep their issue steps for manual `workflow_dispatch`.

User-Agent on every fetch: `digithings-site-smoke/1.0 (+https://github.com/digithings-ai/digithings)`. Per-URL timeout 20s (`AbortSignal.timeout(20_000)`).

HTTP 403 and 429 are warnings (log, do not fail), matching the workflow's bot-challenge rule. Status 0 (no response) is a warning on the freshness check (`INCONCLUSIVE_STATUSES` in `scripts/check_deploy_freshness.py`) and a failure on an asset probe (the shell probe treats `000` as FAIL). Keep that split.

### `smoke-site` (`17 6 * * *`)

Asset probes. Pass is HTTP 200 whose content-type contains the wanted type. HTTP 200 with `text/html` when the wanted type is not `text/html` fails (SPA fallback, #671).

| URL | Wanted content-type |
|---|---|
| `https://digithings.ai/` | `text/html` |
| `https://digithings.ai/docs/` | `text/html` |
| `https://digithings.ai/openwiki/` | `text/html` |
| `https://digithings.ai/openwiki/graph.json` | `application/json` |
| `https://digithings.ai/og.png` | `image/png` |
| `https://digiquant.io/` | `text/html` |
| `https://digiquant.io/dashboard/` | `text/html` |
| `https://digiquant.io/og.png` | `image/png` |

Freshness, ported from `scripts/check_deploy_freshness.py` `evaluate()` (do not shell out to Python). `max_age_hours = 168`. Future skew fail is 24h. Labels match the script: `WARN`, `UNSTAMPED`, `UNREACHABLE`, `MALFORMED`, `STALE`, `PASS`.

| URL | Fail when |
|---|---|
| `https://digiquant.io/build-info.json` | 404, non-JSON 200, missing `built_at`, age > 168h, or stamp more than 24h in the future |
| `https://digithings.ai/build-info.json` | same |

403 / 429 / status 0 on a freshness URL is `WARN` and does not fail the tick.

Keep `workflow: "smoke-site.yml"` and `ref: "develop"` on the job for the override path.

### `smoke-stack` (`27 7 * * *`)

Three GETs. Each must be HTTP 200 and JSON `ok === true` (`GET /healthz` is `{"ok": true}`).

- `https://graph.digithings.ai/healthz`
- `https://key.digithings.ai/healthz`
- `https://search.digithings.ai/healthz`

403 / 429 warn and do not fail. Anything else fails the tick.

digiquant (`:8001`) and digismith (`:8003`) have no public hostname in this replacement. The manual `smoke-stack.yml` compose job still probes them on localhost when a human dispatches it. Do not invent public URLs. Do not run `docker compose` in the container or in the Worker.

Keep `workflow: "smoke-stack.yml"` and `ref: "develop"`.

### `smoke-langsmith`

Leave the workflow and leave it out of `jobs.ts`. Decision is closed: it is not a prod clock, so Phase 4 does not wire it.

---

## Secrets checklist

No new names. Checkpoint archive uses the Phase 1 set already on digiquant-runner. Smokes use no secrets (public GET).

Still absent, and still must stay absent: `FRED_API_KEY`, `GH_ISSUE_TOKEN`, broker credentials, Alpaca keys.

`GITHUB_OVERRIDE_JOBS` stays `""` in `apps/digithings-cron/wrangler.toml`. Setting `checkpoint-archive`, `smoke-site`, or `smoke-stack` in that var is the temporary rollback and burns Actions minutes. Log `github_override` at error. Empty it after the proof.

`printf '%s' "$VALUE" | env -u CLOUDFLARE_API_TOKEN npx wrangler secret put NAME` remains the put command. This plan does not put secrets.

---

## GHA schedule / dispatch notes

- Delete `schedule:` from `pipeline-checkpoint-archive.yml` only, inside the CHR-B PR. Leave `workflow_dispatch`. Add a header comment: the clock is digithings-cron → digiquant-runner; this file is the manual override; do not add `schedule:`.
- Do not delete the workflow. The override path still runs the same two Python steps and still uploads Actions artifacts.
- `smoke-site.yml` and `smoke-stack.yml` already have no `schedule:`. Add one header line each: prod cadence is a digithings-cron probe; `workflow_dispatch` remains; do not add `schedule:`.
- Do not edit `pipeline-digiquant-allocation-shadow.yml`.
- `deploy-digithings-cron.yml` stays on GHA. It is a deploy, and it still syncs `GH_DISPATCH_TOKEN` for twelve-x and the Phase 5 jobs.
- Phase 5 workflows stay `workflow_dispatch` from cron.

---

## Files

This plan PR touches only the two docs rows. The rest are implementation.

| Path | Action |
|---|---|
| `docs/superpowers/plans/2026-10-01-digiquant-phase4-gha-cutover.md` | This plan (this PR). |
| `docs/ops/digiquant-runner.md` | Short pointer. Behavior unchanged until the implementation PRs. |
| `apps/digiquant-runner/commands.json` | CHR-A. Add `checkpoint-archive`. |
| `apps/digiquant-runner/src/commands.ts` | CHR-A. `CommandSpec.publish_if_present?: string[]`. |
| `apps/digiquant-runner/src/commands.test.ts` | CHR-A. |
| `apps/digiquant-runner/container/exec_job.py` | CHR-A. Skip missing `publish_if_present` paths. Required `publish` stays strict. |
| `apps/digiquant-runner/container/exec_job_test.py` | CHR-A. |
| `Dockerfile.digiquant-runner` | CHR-C. Two `COPY` lines. Header records the new Size. No `uv sync` change. |
| `.dockerignore` | CHR-C. Re-include the two scripts. |
| `apps/digithings-cron/src/jobs.ts` | CHR-E replaces the two `wd(...)` smoke rows with `pj(...)`. CHR-B adds `cj(...)` for checkpoint-archive. |
| `apps/digithings-cron/src/dispatch.ts` | CHR-E. `kind: "probe"` branch. Override list still wins. |
| `apps/digithings-cron/src/probe.ts` | CHR-E. Create. URL tables and freshness `evaluate`. |
| `apps/digithings-cron/src/probe.test.ts` | CHR-E. |
| `apps/digithings-cron/src/index.ts` | CHR-B. Strip `dry_run` on checkpoint-archive unless `force`. |
| `apps/digithings-cron/wrangler.toml` | CHR-B. Add `"30 13 * * *"` to `[triggers].crons`. No other cron edits. |
| `apps/digithings-cron/src/jobs.test.ts` | CHR-B and CHR-E. |
| `apps/digithings-cron/src/dispatch.test.ts` | CHR-E. Probe does not call `RUNNER.fetch` or global `fetch` to `api.github.com`. |
| `.github/workflows/pipeline-checkpoint-archive.yml` | CHR-D, inside the CHR-B PR. Delete `schedule:`. Header comment. |
| `tests/scripts/test_checkpoint_archive_workflow.py` | CHR-D. Schedule assertion flips to "schedule key absent". Argv assertions stay. |
| `.github/workflows/smoke-site.yml` | CHR-E. Header comment only. |
| `.github/workflows/smoke-stack.yml` | CHR-E. Header comment only. |
| `apps/digithings-cron/README.md` | CHR-B. Unique-cron count becomes 39 once `30 13 * * *` is added (38 on this SHA). |
| `docs/ops/digiquant-runner.md` | Implementation PR adds the kick and the R2 keys after they exist. This plan PR only points at the plan. |
| `docs/ops/checkpoint-archive-vacuum.md` | CHR-D. One sentence: the pre snapshot for the container path is `pipeline-runs/checkpoint-archive/<run_id>/checkpoint-size-pre.json`. The operator compare is unchanged. |

Do not edit `apps/digithings-stack-cloudflare/**`. Do not edit `digiquant/src/digiquant/ops/checkpoint_archive.py`. Do not edit `digiquant/src/digiquant/portfolio/**` or `digiquant/src/digiquant/research/**`.

---

## Tasks

Human tasks are marked **Human**. CHR ids match the [split](#chr-split-one-assigns-these). Each code task keeps #4822 tests green.

### Task 1 — CHR-A command catalog

**Files:**

- Modify: `apps/digiquant-runner/commands.json`
- Modify: `apps/digiquant-runner/src/commands.ts`
- Test: `apps/digiquant-runner/src/commands.test.ts`

**Interfaces:**

- Consumes: existing `CommandSpec` / `GatedStep`.
- Produces: command `checkpoint-archive` with the JSON above. `CommandSpec.publish_if_present?: string[]`.

- [ ] **Step 1: Write the failing test**

```ts
it("checkpoint-archive matches the workflow and publishes optionally", () => {
  const spec = assertKnownCommand("checkpoint-archive", raw);
  expect(spec.timeout_seconds).toBe(3600);
  expect(spec.concurrency).toBe("checkpoint-archive");
  expect(spec.alias_supabase).toBe(true);
  expect(spec.env).toEqual([
    "CORE_SUPABASE_URL",
    "CORE_SUPABASE_SERVICE_KEY",
    "R2_ACCOUNT_ID",
    "R2_BUCKET",
    "R2_ACCESS_KEY_ID",
    "R2_SECRET_ACCESS_KEY",
    "CORE_POSTGRES_URI",
  ]);
  const flat = JSON.stringify(spec.steps);
  expect(flat).toContain("digiquant_checkpoint_size_gate.py");
  expect(flat).toContain("--snapshot-out");
  expect(flat).toContain("digiquant_archive_checkpoints.py");
  expect(flat).toContain("--retain-days");
  expect(flat).toContain("--manifest-out");
  expect(spec.publish_if_present).toEqual([
    "/tmp/checkpoint-archive-manifests.json",
    "/tmp/checkpoint-size-pre.json",
  ]);
  expect(spec).not.toHaveProperty("failure_issue");
  expect(JSON.stringify(spec)).not.toContain("GH_ISSUE_TOKEN");
  expect(JSON.stringify(spec)).not.toContain("FRED_API_KEY");
});
```

- [ ] **Step 2:** `cd apps/digiquant-runner && npx vitest run src/commands.test.ts` — FAIL (`checkpoint-archive` unknown).
- [ ] **Step 3:** Add the JSON and `publish_if_present` on the type.
- [ ] **Step 4:** Re-run until PASS. `npm run test --workspace digiquant-runner` still passes, including the #4822 cases.
- [ ] **Step 5:** Commit `feat(digiquant): add checkpoint-archive command catalog`.

### Task 2 — CHR-A optional publish

**Files:**

- Modify: `apps/digiquant-runner/container/exec_job.py`
- Test: `apps/digiquant-runner/container/exec_job_test.py`

**Interfaces:**

- Consumes: `publish_if_present` from Task 1.
- Produces: `publish_paths_present(paths: list[str], exists) -> list[str]` drops missing files. `raise_if_required_missing(path: str) -> None` raises `RuntimeError` matching `publish file missing` when the path is not a file. Required `publish` entries call that check. `publish_if_present` entries go through `publish_paths_present` first.

- [ ] **Step 1: Failing test** in `exec_job_test.py`

The file is stdlib (`"""Stdlib checks... No uv, no pytest."""`). Add a `_check_publish_if_present` called from `main()`, same `SystemExit` style as `_check_busy_gate_and_publish_bound`. Do not add pytest.

```python
def _check_publish_if_present() -> None:
    import tempfile

    with tempfile.TemporaryDirectory() as tmp:
        root = Path(tmp)
        present = root / "checkpoint-archive-manifests.json"
        present.write_text("[]", encoding="utf-8")
        missing = root / "checkpoint-size-pre.json"
        kept = exec_job.publish_paths_present(
            [str(present), str(missing)],
            exists=lambda path: Path(path).is_file(),
        )
        if kept != [str(present)]:
            raise SystemExit(f"optional publish kept {kept}")
        try:
            exec_job.raise_if_required_missing(str(missing))
        except RuntimeError as exc:
            if "publish file missing" not in str(exc):
                raise
        else:
            raise SystemExit("required publish must reject a missing file")
```

Keep the existing checks that cover 409 `_running_command` and the 120s publish bound. Wire `_check_publish_if_present()` into `main()` next to them.

- [ ] **Step 2:** `python apps/digiquant-runner/container/exec_job_test.py` fails on the new names.
- [ ] **Step 3:** Implement. `_publish_bounded` still wraps the upload. A dry-run with neither file is a successful no-op publish.
- [ ] **Step 4:** `exec_job_test.py` passes. `npm run test --workspace digiquant-runner` passes.
- [ ] **Step 5:** Commit `feat(digiquant): publish checkpoint artifacts when they exist`.

### Task 3 — CHR-C image

**Files:** `Dockerfile.digiquant-runner`, `.dockerignore`.

- [ ] **Step 1:** Re-include and `COPY` only:

```dockerfile
COPY scripts/digiquant_archive_checkpoints.py ./scripts/digiquant_archive_checkpoints.py
COPY scripts/digiquant_checkpoint_size_gate.py ./scripts/digiquant_checkpoint_size_gate.py
```

```text
# checkpoint-archive (Phase 4, #4761).
!scripts/digiquant_archive_checkpoints.py
!scripts/digiquant_checkpoint_size_gate.py
```

- [ ] **Step 2:** Confirm the `uv sync` lines are byte-identical to `develop`. Confirm `wrangler.toml` still has one `[[containers]]`, `instance_type = "standard-2"`, `max_instances = 1`.
- [ ] **Step 3:** Local image check, no prod credentials:

```bash
docker build -f Dockerfile.digiquant-runner -t digiquant-runner:phase4 .
docker image inspect digiquant-runner:phase4 --format 'Size={{.Size}}'
docker run --rm digiquant-runner:phase4 python -c "import digiquant.ops.checkpoint_archive; print('archive import ok')"
docker run --rm digiquant-runner:phase4 python scripts/digiquant_archive_checkpoints.py --help
docker run --rm digiquant-runner:phase4 python scripts/digiquant_checkpoint_size_gate.py --help
```

`--help` exits 0 and does not open Postgres. Paste `Size` into the PR. If `Size` is not strictly under 12 GiB (12884901888 bytes), stop. Do not change `instance_type`.

- [ ] **Step 4:** Commit `feat(digiquant): bake checkpoint-archive scripts into the standard-2 image`.

### Task 4 — CHR-E probe kind and smokes

**Files:**

- Create: `apps/digithings-cron/src/probe.ts`
- Test: `apps/digithings-cron/src/probe.test.ts`
- Modify: `apps/digithings-cron/src/jobs.ts`
- Modify: `apps/digithings-cron/src/dispatch.ts`
- Modify: `apps/digithings-cron/src/jobs.test.ts`
- Modify: `apps/digithings-cron/src/dispatch.test.ts`
- Modify: `.github/workflows/smoke-site.yml` header
- Modify: `.github/workflows/smoke-stack.yml` header

**Interfaces:**

- Consumes: `fetch` injected into `runProbe(kind, fetchImpl, now)`.
- Produces: `JobKind` includes `"probe"`. `Job.probe?: "site" | "stack"`. `evaluateFreshness(url, status, body, now) -> { label, failed }`. `runSiteProbe` / `runStackProbe` return `{ ok: true }` or throw `Error` whose message contains the first failing URL.

- [ ] **Step 1: Failing tests**

```ts
expect(JOBS.find((job) => job.id === "smoke-site")).toMatchObject({
  kind: "probe",
  probe: "site",
  cron: "17 6 * * *",
  workflow: "smoke-site.yml",
  ref: "develop",
});
expect(JOBS.find((job) => job.id === "smoke-stack")).toMatchObject({
  kind: "probe",
  probe: "stack",
  cron: "27 7 * * *",
  workflow: "smoke-stack.yml",
});

it("site probe passes og.png and fails a text/html fallback", async () => {
  // image/png on https://digiquant.io/og.png -> pass
  // text/html on that same URL -> throw
});

it("freshness treats 403 as a warning and 168h-old built_at as STALE", () => {
  const now = new Date("2026-10-01T00:00:00Z");
  expect(evaluateFreshness("https://digiquant.io/build-info.json", 403, "", now).failed).toBe(false);
  const body = JSON.stringify({ built_at: "2026-09-01T00:00:00Z" });
  const stale = evaluateFreshness("https://digiquant.io/build-info.json", 200, body, now);
  expect(stale.label).toBe("STALE");
  expect(stale.failed).toBe(true);
});

it("stack probe GETs the three public healthz urls and does not call GitHub", async () => {
  // fetch URLs are graph, key, search /healthz
  // global fetch to api.github.com is not called
  // env.RUNNER.fetch is not called
});
```

- [ ] **Step 2:** `npm run test --workspace digithings-cron` FAIL.
- [ ] **Step 3:** Implement `probe.ts` and the dispatch branch. `usesGithub` returns false for `kind: "probe"` unless the id is in `GITHUB_OVERRIDE_JOBS`. Header comments on the two workflow files. Do not add `schedule:`.
- [ ] **Step 4:** Tests PASS. `uniqueEnabledCrons()` still matches `wrangler.toml` (no new cron string in this task).
- [ ] **Step 5:** Commit `feat(digiquant): probe site and stack smokes from digithings-cron`.

Do not set `GITHUB_OVERRIDE_JOBS` in `wrangler.toml` (it stays `""`).

### Task 5 — CHR-B cron flip, including CHR-D schedule delete

**Files:**

- Modify: `apps/digithings-cron/src/jobs.ts`
- Modify: `apps/digithings-cron/src/index.ts`
- Modify: `apps/digithings-cron/wrangler.toml`
- Modify: `apps/digithings-cron/src/jobs.test.ts`
- Modify: `apps/digithings-cron/src/index.test.ts` (or `dispatch.test.ts` if that is where kick args are asserted after #4897)
- Modify: `.github/workflows/pipeline-checkpoint-archive.yml`
- Modify: `tests/scripts/test_checkpoint_archive_workflow.py`
- Modify: `apps/digithings-cron/README.md` cron count
- Modify: `docs/ops/checkpoint-archive-vacuum.md` one sentence on the R2 snapshot key

**Interfaces:**

- Consumes: command `checkpoint-archive` from Task 1. Image from Task 3 already deployed (Task H step 2) before this PR merges.
- Produces: `checkpointArgs(force, bodyArgs) -> Record<string, string>`. `jobsForCron("30 13 * * *")` returns one job.

Ship the workflow edit in this same PR. A follow-up PR that only deletes `schedule:` is out of scope.

- [ ] **Step 1: Failing tests**

```ts
expect(JOBS.find((job) => job.id === "checkpoint-archive")).toMatchObject({
  kind: "container",
  command: "checkpoint-archive",
  concurrency: "checkpoint-archive",
  timeoutSeconds: 3600,
  cron: "30 13 * * *",
  workflow: "pipeline-checkpoint-archive.yml",
  ref: "develop",
  codeRef: "main",
});

it("ordinary checkpoint dispatch sends empty args", async () => {
  // args is {}
  // global fetch not called
});

it("kick without force strips dry_run", async () => { /* sent as {} */ });
it("kick with force keeps dry_run true", async () => { /* args.dry_run === "true" */ });
```

```python
def test_schedule_removed_dispatch_remains() -> None:
    spec = _load()
    on = spec[True]  # YAML 1.1 parses the `on:` key as boolean True
    assert "workflow_dispatch" in on
    assert "schedule" not in on
```

Keep `test_runs_archiver_with_retention` and `test_captures_pre_archive_size_snapshot` and `test_secrets_wired`. The override file still contains those steps.

- [ ] **Step 2:** `npm run test --workspace digithings-cron` FAIL. `pytest tests/scripts/test_checkpoint_archive_workflow.py -m unit` FAIL on the old schedule assertion.
- [ ] **Step 3:** Add the `cj(...)` row. Add `"30 13 * * *"` to `[triggers].crons` next to the other 13:00 entries. Delete the `schedule:` block. Header comment on the workflow. Do not change house-run rows.
- [ ] **Step 4:** Both test commands PASS. `uniqueEnabledCrons()` matches `wrangler.toml`, now including `30 13 * * *`.
- [ ] **Step 5:** Commit `feat(digiquant): point checkpoint-archive at digiquant-runner`.

Do not merge until [Task H](#task-h--human-image-deploy-then-the-clock) step 2 is done. Merging deploys digithings-cron.

### Task H — Human: image deploy, then the clock

Not Phase 3 Task 7. Do not put house secrets here. Do not re-prove house-run.

- [ ] Confirm Phase 3 Task 7 is done and #4897 is merged.
- [ ] Confirm CHR-A and CHR-C are on `develop`.
- [ ] Deploy the runner image. `workflow_dispatch` on `deploy-digiquant-runner.yml` (`environment: production`) or, from `apps/digiquant-runner`:

```bash
printf '%s' "$VALUE" | env -u CLOUDFLARE_API_TOKEN npx wrangler deploy
```

Existing Worker secrets persist. Do not put new names. Confirm the running image is the CHR-C bake (`GET` runner health via the cron binding, or Workers Logs `git_sha`) before the next step.

- [ ] Merge the CHR-B PR. That push deploys digithings-cron and removes the GHA `schedule:` together.
- [ ] Proof kick is a real archive when `dry_run` is omitted. Prefer the next natural `30 13 * * *` tick. To list threads without writing:

```bash
curl -sS -X POST "$CRON_ORIGIN/kick" \
  -H "Authorization: Bearer $CRON_KICK_SECRET" \
  -H "content-type: application/json" \
  -d '{"cron":"30 13 * * *","force":true,"args":{"dry_run":"true"}}'
```

Expect `ok: true` and a `run_id`. Poll `GET /runs/:run_id` until `succeeded`. Workers Logs for that kick contain no `api.github.com` and no `actions/workflows/pipeline-checkpoint-archive.yml`. The Actions tab shows no new run of `Pipeline: checkpoint archive`.

- [ ] A live tick (no `dry_run`) writes `pipeline-runs/checkpoint-archive/<run_id>/checkpoint-archive-manifests.json` when the archive exits 0. The size snapshot object is present only when the advisory step wrote the file.
- [ ] After CHR-E is merged, kick `17 6 * * *` and `27 7 * * *`. Logs list the probe URLs. No `ubuntu-latest` run of `Smoke: site` or `Smoke: stack`. No container boot for those job ids.
- [ ] `GITHUB_OVERRIDE_JOBS` is empty after the proof.
- [ ] After the queue drains, Workers Logs show the container stop within a few minutes (`sleepAfter` 2m). `max_instances` is still 1.

---

## Acceptance checklist

Adapted from epic Phase 4. Sizing follows the Chris lock.

- [ ] `npm run test --workspace digiquant-runner` and `npm run test --workspace digithings-cron` pass.
- [ ] `python apps/digiquant-runner/container/exec_job_test.py` passes.
- [ ] `pytest tests/scripts/test_checkpoint_archive_workflow.py -m unit` passes and asserts `schedule` is absent.
- [ ] `wrangler.toml` on the runner has one container class, `DigiQuantRunnerContainer`, `instance_type = "standard-2"`, `max_instances = 1`.
- [ ] Image `Size` is in the CHR-C PR and is under 12 GiB. The `uv sync` line is unchanged from `5ab8275a8` except the two script copies.
- [ ] `pipeline-checkpoint-archive.yml` has `workflow_dispatch` and no `schedule:`.
- [ ] A 13:30 tick archives in the container. The Actions tab shows no new checkpoint-archive run for that tick.
- [ ] `smoke-site` and `smoke-stack` ticks do not start `ubuntu-latest` and do not start the container.
- [ ] `smoke-langsmith.yml` is still `workflow_dispatch` only and is still absent from `jobs.ts`.
- [ ] House, prices, market-data, tearsheets, onchain, and metrics show zero Actions runs across a weekday, with Phase 3 Task 7 already green. Phase 4 does not re-prove them.
- [ ] `allocation-shadow` `workflow_run` workflows list is still only `Pipeline: dashboard research`.
- [ ] `FRED_API_KEY` and `GH_ISSUE_TOKEN` are unset on the runner. Smokes did not gain a GitHub token.
- [ ] #4822 tests still cover 409 same-command busy, 120s publish bound, and lock held while status is `running`.
- [ ] After the queue drains, the instance is reaped (`sleepAfter` 2m). `max_instances` is still 1.
- [ ] `GITHUB_OVERRIDE_JOBS` is empty in production after the proof.
- [ ] No new public DNS name. No Queues. No second `[[containers]]` block.
- [ ] Phase 5 jobs are still `workflow_dispatch`.

---

## Risks

| Risk | Why it matters | What to do |
|---|---|---|
| Double clock | CHR-B adds a Cron Trigger that deploys on merge to `develop`. The GHA `schedule:` also fires from `develop` until that key is gone. | Schedule delete is a commit in the CHR-B PR, not a later PR. |
| Gap | Deleting `schedule:` without the cron row leaves a day with no archive. | Do not merge a schedule-only PR. |
| Image not deployed | Cron can fire `checkpoint-archive` at an image whose `commands.json` lacks the command. The Worker returns 400. | Task H deploys the CHR-C image before CHR-B merges. |
| Live proof mutates Postgres | `--dry-run` lists threads and returns before R2 writes. Omitting it NULLs bytea for threads older than `--retain-days 1`. | Use the forced dry-run kick to prove the path. Let the next 13:30 tick be the live archive. |
| Overlap at 13:30 | Market-data morning starts at 13:00 with a 1800s budget, so it can still hold a lock at 13:30. | Existing `MAX_INFLIGHT = 2`. One instance. Do not add a second instance to separate them. |
| Optional publish hides a live miss | A live exit 0 that forgot `--manifest-out` would succeed with no R2 object. | The catalog argv includes `--manifest-out`. Acceptance checks the key on a live tick. Dry-run is the case that correctly has no manifest. |
| Smoke misses digiquant / digismith | The prod probe does not call `:8001` or `:8003`. | Those ports are on the manual compose workflow. Say so in the smoke-stack header. Do not publish them. |
| 403 storms | Cloudflare bot challenge from the Worker egress makes every URL a warning, and a dead site looks healthy. | 403/429 stay warnings, matching the GHA job. A string of warnings is visible in Workers Logs. A non-403 failure still throws. |
| Freshness UNSTAMPED | A Pages project that has not rebuilt since `build-info.json` shipped fails the probe. The workflow's issue text already says that is expected once, then a real alarm. | Same rule, Workers Logs instead of a GitHub issue. Do not weaken 404 into a warning. |
| `GITHUB_OVERRIDE_JOBS` left on | Burns the minutes this epic exists to save, and for checkpoint-archive starts `ubuntu-latest` beside the container if someone also re-adds `schedule:`. | Error log. Acceptance requires the var empty. Do not re-add `schedule:`. |
| Last-resort upsize or second class | A second image or `standard-3` / `standard-4` would bill more and add a fleet. The epic's Phase 3 paragraph asked for `DigiQuantHouseContainer` at `standard-4`. Chris rejected it in the Phase 3 plan. | Do not implement. If the image inspect is not under 12 GiB, the implementation PR stops and asks. Shipping a second `[[containers]]` block is a failed Phase 4. |
| Queues or a warm fleet | Either one keeps a consumer or an idle instance awake past the `2m` tail, including on price ticks that do not need checkpoint archive. | Do not add them. The DO queue plus `sleepAfter` 2m is the whole design. |
| #4822 regression | A publish path that ignores the 120s bound, or a second checkpoint process, sticks status on `running` or double-writes R2. | Keep `_publish_bounded` and `_running_command`. New tests must not delete those cases. |
| Phase 3 Task 7 folded in | Two agents put house secrets and deploy the runner at once. | Task 7 stays One-owned and out of this plan. |

---

## Open questions

Instance type is not open. It is `standard-2` on `DigiQuantRunnerContainer`.

`smoke-langsmith` is not open. It stays manual.

No product question blocks CHR-A, CHR-C, or CHR-E. CHR-B waits on the image deploy in Task H, which waits on Phase 3 Task 7.
