# digiquant-runner

Private Cloudflare Container Worker for the digiquant live cadence
(issue #4761, Phases 1–2). No public hostname: `workers_dev = false`, no
custom domain, no routes. digithings-cron is the only clock. It reaches this
Worker over the `RUNNER` service binding.

This Worker does not run the house research chain, broker credentials, Alpaca
keys, or `--execute`. twelve-x stays `workflow_dispatch`. The execution probe
is `--dry-run` only.

## Commands

`apps/digiquant-runner/commands.json` is the allowlist baked into the image.

| Cron job | Command | Notes |
| --- | --- | --- |
| `market-data-refresh-morning` (`0 13 * * *`) | `market-data-refresh` | |
| `market-data-refresh-evening` (`30 21 * * *`) | `market-data-refresh` | Same concurrency group |
| `prices-fx-refresh` / `prices-fx-refresh-sun` | `prices-fx-candles` | No `fetch-macro` |
| `prices-at-open-13` / `prices-at-open-14` | `prices-at-open` | ET open gate still applies |
| `prices-eod-macro` | `prices-eod-macro` | `fetch-macro` only when `run_writers=true` |

`prices-fx-refresh-writers` is in the catalog and is not a cron row. Cron
never sends `run_writers`. A kick can pass `args`.

## Phase 2 commands

Same container class (`DigiQuantRunnerContainer`, `standard-2`). The image
sync adds `--extra nautilus` for tearsheets and research-metrics. The
nautilus 1.230.0 cp312 manylinux x86_64 wheel is 182608916 bytes, under the
~8 GB split, so there is no `DigiQuantRunnerNautilusContainer`. `ccxt` stays
out of the lockfile; the Coinbase step is `uv run --frozen --with ccxt`.

| Cron job | Command | Timeout | Notes |
| --- | --- | --- | --- |
| `onchain` (`40 22 * * *`) | `onchain-bitview` | 900s | `fetch-bitview --supabase` |
| `execution-cron-check` (`15 12 * * *`) | `execution-cron-check` | 600s | Five probe steps. Later steps still run after an earlier failure. No `--execute`, `--all`, or `portfolio.chain` |
| `research-metrics` (`5 22 * * *`) | `research-metrics` | 1200s | finalize (continue on error) → verify `--write` → metrics → read-only verify → attribution (`always`). Empty `date` is the no-date branch |
| `tearsheets` (`12 0 * * *`) | `tearsheets` | 2700s | calibrations → Coinbase (`--with ccxt`) → `export_sdca_macro.py` if present → `generate_tearsheets.py` |

Image pin stays released `main`. Probe CLIs (`scripts/execution_cron_check.py`,
`digiquant.dashboard.overlay`, `digiquant.execution.sync_cron`,
`digiquant.execution.route_cron`, `digiquant.notify.dispatch`) are on `main`,
so this job is cut over. Do not point the container at `develop`.

A kick can pass `args.date` (`YYYY-MM-DD`) for research-metrics. Cron sends
no date, which selects `--mark-through <UTC today>` on the NAV write,
`--mark-through-book` on metrics, and the no-date finalizer and attribution
commands. Exit 3 from metrics when there is no book is a real failure.

The runner does not file GitHub issues (`GH_ISSUE_TOKEN` is not a binding;
`commands.json` has no `failure_issue`). The GHA override files still carry
`<!-- digiquant-tearsheets-tracker -->` and
`<!-- digiquant-onchain-bitview-tracker -->`. Container failures show up in
Workers Logs and `GET /runs/:run_id`.

These workflows already have no `schedule:`. Do not add one. House-run is
still `repository_dispatch`.

## Macro panel (#4794)

`market-data-refresh` seals the macro panel from anonymous Gloomberb
`econ_series` pages — no `FRED_API_KEY` is read, set, or required. Chris
locked abandon-FRED; a set key does not dual-write.

- `market-data-refresh` refreshes the 23 kept panel ids
  (`digiquant.data.prices.gloomberb_macro.KEPT_SERIES_IDS`): newest page per
  series merged into the existing `fred__*` generation, sealed rows older
  than the page kept. History before a 1000-row bootstrap tail is whatever
  was already sealed.
- The 8 dropped ids are never fetched. Their `latest` pointers keep serving
  the last seal. Do not re-add them without a probe.
- `prices-eod-macro` with `run_writers=true` runs `fetch-macro` the same way
  (Gloomberb panel + Yahoo). The artifact records `fred_skipped: []`.

`prices-intraday` is removed. Do not start a container to echo that no-op.

## Kick

`POST /kick` on digithings-cron (Bearer `CRON_KICK_SECRET`) awaits the runner
POST and returns `runs: [{ job_id, run_id, status }]`. `scheduled()` does not
await the container job.

```bash
curl -sS -X POST "$CRON_ORIGIN/kick" \
  -H "Authorization: Bearer $CRON_KICK_SECRET" \
  -H "content-type: application/json" \
  -d '{"cron":"0 13 * * *"}'
```

`force: true` skips the ET open gate for that kick only. Cron triggers never
set `force`.

Writers-stop (#3780) stays. To run the gated steps once:

```bash
curl -sS -X POST "$CRON_ORIGIN/kick" \
  -H "Authorization: Bearer $CRON_KICK_SECRET" \
  -H "content-type: application/json" \
  -d '{"cron":"27 21 * * MON-FRI","args":{"run_writers":"true"}}'
```

Without that arg, eod runs `sync-calendar` only. `prices-fx-refresh-writers`
with empty args has no steps and exits 0. It is not on a cron.

`GET /runs/:run_id` on digithings-cron proxies to runner `GET /v1/jobs/:id`
with `RUNNER_AUTH_TOKEN`. Same kick bearer. Missing `CRON_KICK_SECRET` is 404.

## Logs and artifacts

Workers Logs are on for both Workers (`[observability] enabled = true`).

A successful refresh publishes the manifest into the `digithings-archive`
bucket at:

`pipeline-runs/market-data-refresh/<run_id>/market-data-refresh.json`

## Image pin

The image is the released `main` tree baked at build time. The hot path is
`uv run --frozen --no-sync`, except Coinbase tearsheet fetch which is
`uv run --frozen --with ccxt`. `/healthz` reports `git_sha` from the latest
stored job status (`DIGIQUANT_RUNNER_GIT_SHA`). Until a job has run, that
value is `unknown`. Wrangler does not pass a build arg. A non-wrangler build
can set it:

```bash
docker build -f Dockerfile.digiquant-runner \
  --build-arg GIT_SHA="$(git rev-parse --short HEAD)" .
```

One pinned Durable Object id: `runner-v1`. `max_instances = 1`,
`instance_type = standard-2`. Idle `sleepAfter` is 2m; a held lock extends
it to 30m. The heartbeat calls container `GET /status` about every 60s.

Concurrency: the Durable Object ledger is primary (one lock per concurrency
group, `MAX_INFLIGHT = 2`). The container also refuses a twin `POST /run` for
the same command while a status file is still `running` (HTTP 409) — that
backstops a premature DO watchdog timeout so two `market-data-refresh`
processes cannot race the same R2 generation keys. The DO watchdog aligns to
the container `started_at` and does not release a lock while `/status` still
reports `running`; it only ledger-times-out when the container is unreachable
past `timeout_seconds + 120s`. Artifact `publish` is bounded to 120s so status
cannot stick on `running` forever.

## Rollback

`GITHUB_OVERRIDE_JOBS` on digithings-cron defaults to empty, so migrated jobs
never call `api.github.com`. Set it to a comma-separated list of job ids to
send those ids down the existing `workflow_dispatch` path. A non-empty hit
logs `github_override` at error.

Re-enabling `pipeline-market-data-refresh.yml` does not restore a clock. The
`schedule` key was removed. Manual `workflow_dispatch` still works.

## Secrets

Set these in the Cloudflare dashboard (or `wrangler secret put`) before the
first deploy. This PR does not deploy and does not put secrets.

On digiquant-runner: `RUNNER_AUTH_TOKEN`, `R2_ACCOUNT_ID`, `R2_BUCKET`,
`R2_ACCESS_KEY_ID`, `R2_SECRET_ACCESS_KEY`, `CORE_POSTGRES_URI`,
`CORE_SUPABASE_URL`, `CORE_SUPABASE_SERVICE_KEY`.

Phase 2 adds `CLOUDFLARE_EMAIL_API_TOKEN`, `CLOUDFLARE_ACCOUNT_ID`, and
`NOTIFY_FROM` for `execution-cron-check`. Missing names fail that probe
closed (exit 2). Research-metrics and tearsheets do not need LLM, digikey,
or LangSmith keys. Those stay off this Worker until the house run.

`FRED_API_KEY` is gone from this path and must stay unset. #4794 PR3
(#4817) removed the last FRED callers, including tearsheet
`export_sdca_macro.py`, which stages M2SL from Supabase or sealed R2 and
does not call `fetch_fred`. Do not put `FRED_API_KEY` back on the runner.
`GH_ISSUE_TOKEN` is not used: the runner does not open or update GitHub
issues.

On digithings-cron: the same `RUNNER_AUTH_TOKEN` value.

No broker credentials and no Alpaca keys.

`CLOUDFLARE_API_TOKEN` is also wrangler's own auth variable. Unset it for
the wrangler process:

```bash
printf '%s' "$VALUE" | env -u CLOUDFLARE_API_TOKEN npx wrangler secret put NAME
```

## Phase 2 kicks

```bash
curl -sS -X POST "$CRON_ORIGIN/kick" \
  -H "Authorization: Bearer $CRON_KICK_SECRET" \
  -H "content-type: application/json" \
  -d '{"cron":"40 22 * * *","force":true}'
```

The same shape covers `12 0 * * *` (tearsheets), `5 22 * * *`
(research-metrics), and `15 12 * * *` (execution probe). Pass
`"args":{"date":"YYYY-MM-DD"}` only when recomputing one metrics day.

## Phase 3 note

Phases 1–2 do not run the house research chain and do not write the
skip-if-done ledger. A same-day GitHub Actions manual house success does not
write `pipeline-runs/house-run/<YYYY-MM-DD>/success.json`.
