# twelvex-runner

On-demand Cloudflare Container for two twelve-x jobs that today burn GitHub
Actions minutes:

| Cron job | Schedule (UTC) | Route | Command |
| --- | --- | --- | --- |
| `twelve-x-market-context-intraday` | `4 */4 * * *` | `POST /run/ingest` | `python -m twelve_x.scripts.ingest_market_context intraday` |
| `twelve-x-market-context-daily` | `30 5 * * *` | `POST /run/ingest` | `... daily` |
| `twelve-x-market-context-weekly` | `8 7 * * SAT` | `POST /run/ingest` | `... weekly` |
| `twelve-x-primemarket-heartbeat` | `3 6,18 * * *` | `POST /run/heartbeat` | `python -m twelve_x.scripts.primemarket_session_heartbeat` |

`digithings-cron` calls this Worker over the `TWELVEX_RUNNER` service binding.
A job id listed in `GITHUB_OVERRIDE_JOBS` stays on `workflow_dispatch`.

The container class is `TwelveXRunnerContainer`: `instance_type = "basic"`,
`max_instances = 1`, `sleepAfter = "2m"`. It starts per call. There is no
public hostname.

## Auth

`POST /run/*` requires `Authorization: Bearer $RUNNER_AUTH_TOKEN`. `GET /healthz`
does not, and it does not start the container.

## DRY_RUN

`DRY_RUN=1` on this Worker still starts the container and POSTs
`{"dry_run": true}`. The image returns exit 0 and does not exec the twelve-x
command, so nothing is written. `DRY_RUN=1` on `digithings-cron` does not call
this Worker at all.

## Alerts

Failure uses the same GitHub labels as the workflows, on `digithings-ai/twelve-x`:

- ingest exit 1 (and any other non-zero except 2) → `market-context-failure`
- ingest exit 3 → `market-context-transport-failure`
- ingest exit 2 → no alert (the heartbeat owns session expiry)
- heartbeat non-zero → `primemarket-session-expired` (assigned to `chrizefan`)
- heartbeat exit 0 → comment and close open `primemarket-session-expired` issues

A fresh open issue inside 24 hours gets a comment instead of a new issue.
Logs record job, start, exit, and duration. They do not record the log tail
or any secret.

## Secrets to set before a deploy

Names only. Never commit values. `printf '%s' "$VALUE" | env -u CLOUDFLARE_API_TOKEN npx wrangler secret put NAME`

| Name | Where |
| --- | --- |
| `RUNNER_AUTH_TOKEN` | this Worker and `digithings-cron` (already on cron) |
| `GH_ISSUES_TOKEN` | this Worker. Issues read/write on `digithings-ai/twelve-x` only |
| `PRIMEMARKET_SESSION_TOKEN` | this Worker, forwarded into the container |
| `TWELVEX_SUPABASE_SERVICE_KEY` | this Worker, forwarded into the container |
| `TWELVEX_SUPABASE_URL` | optional. twelve-x has a code default |

Not required for these jobs: `CHEAPERINFERENCE_API_KEY`, `TWELVEX_R2_ACCOUNT_ID`,
`TWELVEX_R2_ACCESS_KEY_ID`, `TWELVEX_R2_SECRET_ACCESS_KEY`, `TWELVEX_R2_BUCKET`,
`SUPABASE_DB_URL`. The workflow env blocks do not pass them. Ingest writes
Supabase through the service key. It does not call an LLM and it does not write R2.

Image build (not a Worker secret): a BuildKit secret `github_token` with
contents read on `twelve-x` and `digithings`, because `pip install -e .` clones
private digithings packages. The pin is `twelvex-ref.txt`.

## Deploy order

Do not deploy without the DevOps Lead's check-off.

1. Build and deploy this Worker, then put the secrets above.
2. Deploy `digithings-cron` with the `TWELVEX_RUNNER` binding.
3. Leave the four ids in `GITHUB_OVERRIDE_JOBS` until each job has one
   successful container run (logs plus data landed). Then clear those ids.
4. A later twelve-x change may drop any remaining `schedule:` triggers.
   Keep `workflow_dispatch`. The workflows in twelve-x already have no
   `on.schedule`; the clock is `digithings-cron`.

FX hub (`digiquant.io/dashboard/twelve-x/`) must stay up. After a production
deploy, check `graph.digithings.ai/health` and the dashboard, and roll back
on breakage.

`instance_type = "basic"` is about 1/4 vCPU and 1 GiB. If the image or the
process does not fit, bump the instance type. Do not switch these jobs to the
container until that check passes.
