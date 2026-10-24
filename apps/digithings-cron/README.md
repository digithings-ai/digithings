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
- src/triggers.ts — the required-trigger contract, as data, and its evaluator
- src/trigger-alarm.ts — the alarm transport for both trigger fault classes
- scripts/fetch-deployed-triggers.mjs — prints the DEPLOYED cron list as JSON (observes only)
- src/index.ts — scheduled + GET /healthz + optional POST /kick and GET /runs/:id

## Env

- Secret GH_DISPATCH_TOKEN (required for real GitHub dispatch)
- Optional secret CRON_KICK_SECRET (enables POST /kick and GET /runs/:id)
- Secret RUNNER_AUTH_TOKEN (Bearer for kind `container`; required outside dry-run)
- Var DRY_RUN = "0" by default; "1" logs intended POST only
- Var GITHUB_OVERRIDE_JOBS = "" (comma-separated job ids that stay on GitHub)
- Var ALERT_ISSUE_REPO / ALERT_ISSUE_NUMBER — where cron alarms post. Not secrets.
  Currently `digithings-ai/digithings` #4761.

Set secrets from this directory with wrangler secret put (never echo values).

## The required-trigger contract (DIG-732)

`src/triggers.ts` holds the explicit set of crons the FX pipeline requires, as
data, each with the reason it is required: the three session crons
(`twelve-x-asia`, `twelve-x-london`, `twelve-x-new-york`), the session
catch-up (`twelve-x-session-catchup`), and the session heartbeat
(`twelve-x-primemarket-heartbeat`).

The set is deliberately NOT derived from the job rows. DIG-553 Finding 1
measured over 543 runs: 1-30 August 2026 produced zero catch-up runs, and six
of the twelve client-visible stale days were therefore unrecoverable, with
nothing saying so. Deriving the expected triggers from `JOBS` is what made that
invisible — delete the catch-up row *and* its cron line together and every
assertion derived that way stayed green.

Two assertions, one implementation:

1. **Repo side**, always. `src/triggers.test.ts` parses the committed
   `wrangler.toml` and evaluates the contract against it. A required trigger
   missing from the repo fails the suite.
2. **Deployed side**, in CI. `scripts/fetch-deployed-triggers.mjs` reads
   `GET /accounts/{account_id}/workers/scripts/{script_name}/schedules` and the
   same test evaluates the contract against that list. Locally it is skipped,
   because there is no deployment to ask.

Both run inside the deploy workflow's `Test + typecheck` step, before
`wrangler deploy`. **An unmet contract fails the deployment.** The fetch script
exits non-zero rather than printing an empty list, so a failed API call fails
the gate instead of reporting five false alarms.

### Two fault classes, and they read differently

| Class | Meaning | Where it fires |
| --- | --- | --- |
| `required_cron_absent` | A required trigger is **not deployed**. Nothing will fire it. Cover is lost. | The contract check, at deploy time |
| `unmapped_cron` | A cron **is deployed** that no enabled job claims. It fires, and dispatches nothing. Cover is being burned. | `scheduled()`, at tick time |

`unmapped_cron` was a bare `console.error` line before DIG-732. It is now an
alarm on the same GitHub-issue-comment path the other twelve-x alarms use, via
`src/trigger-alarm.ts`. The transport reuses `GH_DISPATCH_TOKEN` (Issues:
write); that coupling is risk R14 in `docs/ops/SECRETS_INVENTORY.md`, accepted
by Chris on 2026-10-05.

Two deliberate non-alarms, both pinned by tests:

- A cron whose only job rows are **disabled** is a paused trigger, not a fault.
  It logs and stays quiet. Paging on it would be the wolf-cry that gets a
  control switched off.
- `POST /kick` of an unmapped cron is a **probe**, not a deployed trigger.

### Limits

One extra subrequest per raise, at most one raise per cron firing, and it only
ever happens on a path that dispatched nothing — so it cannot cost a dispatch.
Bodies are a few hundred bytes, well inside GitHub's 65536-byte comment limit.
No storage, no CPU of note. Alarm delivery failure is logged and swallowed: an
alarm that throws turns a bad deployment into a crashing Worker, and the
operator then has two faults instead of one.

## Unique crons

`wrangler.toml` `[triggers].crons` matches `uniqueEnabledCrons()` in order
(38 expressions). House-run is
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
through the wrangler-action secret input without printing the value. The same
CI token reads the deployed trigger list first (Workers Scripts Read); the
contract assertion is part of `Test + typecheck`, so a deploy that would drop a
required trigger does not happen.

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
