# digithings-cron

Org-wide Cloudflare Worker that owns production clocks for digithings-ai (#3579).

Replaces unreliable GitHub Actions schedule triggers with Cloudflare Cron Triggers
that dispatch workflow_dispatch / repository_dispatch on the default `develop` branch of
digithings-ai/digithings and digithings-ai/twelve-x (FX Hub).

Price and market-data jobs (`kind: container`) POST the private digiquant-runner
Worker over the `RUNNER` service binding (#4761). This Worker still has no
Containers of its own. twelve-x stays `workflow_dispatch`. Default branch stays
develop. `GITHUB_OVERRIDE_JOBS` defaults to empty; a listed job id falls back to
workflow_dispatch and logs `github_override` at error.

## Layout

- wrangler.toml — name digithings-cron, triggers crons, DRY_RUN, RUNNER binding
- src/jobs.ts — typed job map (`kind` includes `container`)
- src/dispatch.ts — GitHub API dispatch, or POST digiquant-runner
- src/et-open.ts — season-specific America/New_York 09:30 gate
- src/backfill.ts — pure plan builder for POST /backfill (allowlist, date validation)
- src/backfill-do.ts — BackfillLedger Durable Object, per-date idempotence
- src/index.ts — scheduled + GET /healthz + optional POST /kick, POST /backfill, GET /runs/:id

## Env

- Secret GH_DISPATCH_TOKEN (required for real GitHub dispatch)
- Optional secret CRON_KICK_SECRET (enables POST /kick, POST /backfill, GET /runs/:id)
- Secret RUNNER_AUTH_TOKEN (Bearer for kind `container`; required outside dry-run)
- Var DRY_RUN = "0" by default; "1" logs intended POST only
- Var GITHUB_OVERRIDE_JOBS = "" (comma-separated job ids that stay on GitHub)
- Var BACKFILL_ENABLED = "0" by default; "1" enables POST /backfill (404 `backfill_disabled` otherwise)
- DO binding BACKFILL_LEDGER → class BackfillLedger (SQLite-backed; needs a migration tag)

Set secrets from this directory with wrangler secret put (never echo values).

## Unique crons

`wrangler.toml` `[triggers].crons` matches `uniqueEnabledCrons()` in order
(37 expressions after twelve-x digisearch parity). House-run is
weekly Monday morning only (`house-run-09` at `17 9 * * MON`); daily
`house-run-10/11/12` stay in `src/jobs.ts` with `enabled: false`.
`checkpoint-archive` is live at `30 13 * * *` on digiquant-runner.
GHA `schedule:` stays off — this Worker is the SSOT. Leftover sweep after
#4970: develop YAML has zero `on.schedule` keys; `digisearch_parity` is
not a workflow in this repo. Path A traps
(`agent-pr-finalizer`, `agent-backlog-snapshot`, `refresh-repo-activity`,
`project-enforce-assignment`) are live `workflow_dispatch` jobs; their
YAML is dispatch-only. twelve-x-new-york is weekday-only
on `17 12 * * MON-FRI`. `twelve-x-digisearch-parity` is weekly Monday
09:08 UTC (`8 9 * * MON`; GHA was `0 9 * * 1`, offset avoids house-run-09).

## Snapshot backfill (POST /backfill)

`POST /backfill` is the sanctioned dispatch path for **dated** `fx_confluence_snapshot`
backfills in twelve-x. It is **not a job and not a clock**: there is no `JOBS` row for
it, no `cron`, and no `[triggers]` expression. Nothing fires it on a schedule; a human or
an agent POSTs it.

### Why it is not a `wd()` row

`src/jobs.ts` carries the rule *"Add a twelve-x `wd()` row only with a known cron from
that repo."* A dated remediation has no twelve-x cron — its schedule is "the day we decide
to run it", which is not a cron expression. An earlier attempt modelled it as a `wd()` row
with an invented `0 0 30 2 *` (February 30) cron plus `enabled: false`, which is precisely
the shape the rule forbids. This endpoint drops that fiction: no row, no cron, no
`enabled` flag. The checkable form is `git diff origin/develop -- src/jobs.ts` being empty.

### Input contract

Body is JSON with an allowlist of exactly two keys, `BACKFILL_INPUT_KEYS`:

- `dates` — **required**. Comma-separated `YYYY-MM-DD` run dates to re-stamp.
- `force_dates` — optional, must be the string `"true"`. Re-dispatches dates already
  recorded as remediated.

Anything else is refused with `400 unexpected_arg`, naming the key. That includes the two
keys upstream does accept and this endpoint deliberately does not:

- **`run_date` is never accepted.** It belongs to `daily_run.yml`, not `maintenance.yml`.
  A wrong key makes GitHub return `422` while the caller believes it succeeded and starts
  zero runs — the 2026-09-28 outage shape, whose cause was only in the second log line.
- **`since` / `until` are not accepted** even though `maintenance.yml` supports them. A
  date *range* cannot be made idempotent per date from this Worker — it cannot enumerate
  stored `run_dates` — and a range is the unbounded shape that produced the original
  surplus. Exact dates are what make the per-date no-op guarantee below provable.

Cap: `MAX_BACKFILL_DATES = 32` after dedupe (`400 too_many_dates`). Non-existent dates
such as `2026-02-30` are rejected (`400 invalid_dates`, names the element) rather than
silently reaching twelve-x.

### Idempotence per date

`BackfillLedger` is a Durable Object, chosen over KV because KV has no atomic
read-modify-write — two overlapping kicks could both read "absent" and both dispatch.
`claim()` runs inside a single `storage.transaction`, so exactly one caller wins a date.

- First POST for a date dispatches it and records it `done`.
- A repeat POST for an already-remediated date is a **no-op**: `200` with
  `{"dispatched": [], "already_remediated": true}` and **zero** upstream requests.
- An in-flight date is never stolen, even with `force_dates`.
- A dispatch failure releases its claims, so a retry is still possible.
- Under `DRY_RUN=1` nothing is recorded, so a preview cannot mark a date remediated.

This is the property that makes the endpoint safe to leave armed: a re-fire of a date set
cannot rebuild the surplus that a second backfill of the same date created once already.

### Guard ladder

Every rung runs before the first request leaves the Worker:

| Condition | Response |
| --- | --- |
| `CRON_KICK_SECRET` unset | 404 |
| Bad bearer | 401 |
| `BACKFILL_ENABLED !== "1"` | 404 `backfill_disabled` |
| Body not JSON | 400 `invalid_json` |
| Non-object body, or a non-string value | 400 `invalid_args` |
| Key outside the allowlist | 400 `unexpected_arg` |
| `force_dates` present and not `"true"` | 400 `invalid_args` |
| **`dates` missing or blank (bare kick)** | **400 `missing_required_arg`** |
| Splits to no dates | 400 `invalid_dates` |
| Element is not a real calendar date | 400 `invalid_dates` |
| More than 32 dates | 400 `too_many_dates` |
| `BACKFILL_LEDGER` binding absent | 503 `backfill_unconfigured` |
| GitHub dispatch failed | 502 `dispatch_failed` (claims released) |

Success dispatches `maintenance.yml` on `digithings-ai/twelve-x` at `ref: develop` with
inputs `{backfill_snapshots: "true", dates: "<csv>"}` only.

```
curl -X POST https://digithings-cron.<account>.workers.dev/backfill \
  -H "Authorization: Bearer $CRON_KICK_SECRET" \
  -H "Content-Type: application/json" \
  -d '{"dates":"2026-06-02,2026-06-03"}'
```

Scope is `fx_confluence_snapshot` only. `fx_trade_ideas_snapshot` is never written or
pruned by this path (twelve-x `tests/test_backfill_snapshots.py`).

### Deployment caution

Any push touching `apps/digithings-cron/**` deploys this Worker to production (see
`## Deploy`). A PR against `develop` is therefore a production change. Nothing here is
enabled by default: `BACKFILL_ENABLED = "0"` in `wrangler.toml`, and turning it on is a
separate, explicit act.

**Prerequisite:** twelve-x `maintenance.yml` is currently `disabled_manually`, and GitHub
refuses to dispatch a disabled workflow. Until it is re-enabled, `POST /backfill` will
record claims and get a benign 422 — treat that as *not yet live*, not as success.

## Local

```
cd apps/digithings-cron
npm install && npm test && npm run typecheck
npm run dev
# curl http://127.0.0.1:8787/__scheduled?cron=...
```

## Deploy

Deploy from `develop` and `main`. CI workflow:
.github/workflows/deploy-digithings-cron.yml (push paths
apps/digithings-cron/** + workflow_dispatch; Node 22; wrangler deploy).
Needs CLOUDFLARE_API_TOKEN + CLOUDFLARE_ACCOUNT_ID and syncs GH_DISPATCH_TOKEN
through the wrangler-action secret input without printing the value.

## Migration

digithings: schedule blocks removed in this PR, workflow_dispatch / repository_dispatch kept.

twelve-x follow-up (other repo): remove schedule from daily_run_asia/london/new_york,
market_context_ingest (keep bucket input), performance_eval, primemarket_session_heartbeat,
session_catchup, digisearch_parity_check; keep workflow_dispatch; add header pointing at
digithings-cron.

## Jobs

See src/jobs.ts for the full enabled map. market_context uses bucket inputs
intraday / daily / weekly. agent-pr-finalizer dispatches with `dry_run=false`.
twelve-x-archive-maintenance dispatches with `dry_run=false` and
`dump_before_prune=true`. `twelve-x-digisearch-parity` dispatches
`digisearch_parity_check.yml` with no inputs (workflow default days=14).
House-run is `kind: container`
(`house-run-09` Monday 09:17 UTC). Price jobs, market-data-refresh,
checkpoint-archive, onchain, tearsheets, research-metrics, and
execution-cron-check use `kind: container`. Those workflows have no
`schedule:` of their own. The runner command catalog is
`apps/digiquant-runner/commands.json`. Operator notes:
`docs/ops/digiquant-runner.md`.
