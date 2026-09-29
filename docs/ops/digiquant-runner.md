# digiquant-runner (Phase 1)

Private Cloudflare Container Worker for the digiquant live cadence
(issue #4761, Phase 1 only). No public hostname: `workers_dev = false`, no
custom domain, no routes. digithings-cron is the only clock. It reaches this
Worker over the `RUNNER` service binding.

Phase 1 does not run the house research chain, `execution-cron-check`, broker
credentials, Alpaca keys, or `--execute`. twelve-x stays `workflow_dispatch`.

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
`uv run --frozen --no-sync`. `/healthz` reports `git_sha` from the latest
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

On digiquant-runner: `RUNNER_AUTH_TOKEN`, `GH_ISSUE_TOKEN` (Worker only, not
injected into the container), `R2_ACCOUNT_ID`, `R2_BUCKET`,
`R2_ACCESS_KEY_ID`, `R2_SECRET_ACCESS_KEY`, `FRED_API_KEY`,
`CORE_POSTGRES_URI`, `CORE_SUPABASE_URL`, `CORE_SUPABASE_SERVICE_KEY`.

On digithings-cron: the same `RUNNER_AUTH_TOKEN` value.

No broker credentials and no Alpaca keys.

`CLOUDFLARE_API_TOKEN` is also wrangler's own auth variable. Unset it for
the wrangler process:

```bash
printf '%s' "$VALUE" | env -u CLOUDFLARE_API_TOKEN npx wrangler secret put NAME
```

## Phase 3 note

Phase 1 does not run the house research chain and does not write the
skip-if-done ledger. A same-day GitHub Actions manual house success does not
write `pipeline-runs/house-run/<YYYY-MM-DD>/success.json`.
