# twelvex-runner

On-demand Cloudflare Container for the twelve-x jobs that today burn GitHub
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

## The FX research session route

`POST /run/session` body:

```json
{"session": "asia", "run_date": "2026-10-01", "dry_run": false}
```

`session` is one of `asia`, `london`, `new_york`. The route mirrors the
twelve-x `daily_run_reusable.yml` job: the container runs
`python -m twelve_x.scripts.ingest_calendar` first (not fatal, like the
workflow step with `continue-on-error`) and then `python -m twelve_x.graph`,
which decides the exit code. The graph step runs with `FX_SESSION=<session>`
and `TRADE_INTELLIGENCE_MODE=alongside`.

`run_date` is optional and is the workflow's backfill input. It must be a
calendar date in `YYYY-MM-DD` form. The Worker answers `400 invalid_run_date`
for anything else and the container checks it a second time, so a malformed
date never reaches the graph. An empty string counts as no `run_date`, like
the workflow's empty default. The dispatcher in `digithings-cron` trims the
value and reads an empty one as no date, the same way the Worker does, so a
padded date in a job row is forwarded clean. With no `run_date` the graph takes its forward
high-water-mark path. The three daily session crons pass none, so they keep
the forward path.

Only the session route takes a `run_date`. The Worker drops it on the
ingest and heartbeat routes, and the dispatcher in `digithings-cron`
sends it only for a session job. Only the graph step receives it: the
calendar step runs without it. The graph step always carries `RUN_DATE`,
empty for the forward path, and the container never inherits a date from
its own environment.

The code that runs each command lives in one place only: `container/server.py`.
Do not copy an argv into the TypeScript. The tables above are a copy for
humans. The pinned twelve-x ref carries exactly one heartbeat script,
`scripts/primarket_session_heartbeat.py`, and no second spelling of that
name, so a second copy of the name would drift without any run failing. A
test in `container/server_test.py` scans the whole app and fails on any
other module path or any copy of an argv.

## Auth

`POST /run/*` requires `Authorization: Bearer $RUNNER_AUTH_TOKEN`. `GET /healthz`
does not, and it does not start the container.

## Durable Object recycle

The platform recycles the container Durable Object instance on its own
schedule. When that happens mid-request the hop fails with:

```
Connection closed: this Durable Object instance is no longer active. Reconnect or retry the request.
```

The Worker reconnects once and repeats the request against a fresh stub of the
binding. If that reconnect fails too, the Worker answers `503` with
`Retry-After: 30` and body:

```json
{ "error": "durable_object_unavailable", "detail": "the runner's Durable Object instance was not available; retry later" }
```

The answer is retryable on purpose: a caller that honours `Retry-After` waits
that window, the platform starts a new instance and the request lands. The
caller today (`digithings-cron`) does not read the header, so a `503` fails
that cycle of the job loudly instead of being retried in the same request. A
failure that is not a Durable Object recycle is not retried and is not masked.
The reconnect lives in `@digithings/durable-object-reconnect`, shared with the
other container Workers.

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
Logs record job, start, exit, duration and the one line reason of a failed
run. They do not record the log tail or any secret.

## The reason of a failed run

A reason that stays inside the container is a reason the run watch cannot
read, so the reason travels with the exit:

- the container keeps the head and the tail of the log. The ingest prints its
  verdict line on stdout and stdout comes first, so a log that keeps only the
  end drops the line that names the cause.
- the Worker reads the reason off the log tail and puts it in the exit log
  line, in the response body and in the alert.
- `digithings-cron` logs the reason and puts it in the error it throws. That
  message is what the Worker error column holds.

The reason is one line. It is never a secret: the container redacts the log
before it leaves the image.

The pinned twelve-x prints one machine-readable line per failed exit, and
splits a transport failure into exit 3:

    MARKET_CONTEXT_VERDICT=source: 2 source(s) failed: dmx-overview

Both come from the twelve-x head in `twelvex-ref.txt`. An older pin has
neither: the Worker then falls back to the `market_context:` log marker and
then to the last line the run said.

## Secrets to set before a deploy

Names only. Never commit values. `printf '%s' "$VALUE" | env -u CLOUDFLARE_API_TOKEN npx wrangler secret put NAME`

| Name | Where |
| --- | --- |
| `RUNNER_AUTH_TOKEN` | this Worker and `digithings-cron` (already on cron) |
| `GH_ISSUES_TOKEN` | this Worker. Issues read/write on `digithings-ai/twelve-x` only |
| `PRIMEMARKET_SESSION_TOKEN` | this Worker, forwarded into the container |
| `TWELVEX_SUPABASE_SERVICE_KEY` | this Worker, forwarded into the container |
| `TWELVEX_SUPABASE_URL` | optional. twelve-x has a code default |
| `CHEAPERINFERENCE_API_KEY` | the session route only. The model key, forwarded into the container as `OPENAI_API_KEY` |
| `CORE_SUPABASE_SERVICE_KEY` | the session route only. The shared core calendar writes |

`OPENAI_API_BASE` is not a secret. It is the model endpoint the house path
uses, a plain var on this Worker (`[vars]` in `wrangler.toml`) with the same
literal the twelve-x workflow job env carries.

Not required for the ingest and heartbeat jobs: `TWELVEX_R2_ACCOUNT_ID`,
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
