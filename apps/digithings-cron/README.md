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
- src/index.ts — scheduled + GET /healthz + optional POST /kick and GET /runs/:id

## Env

- Secret GH_DISPATCH_TOKEN (required for real GitHub dispatch)
- Optional secret CRON_KICK_SECRET (enables POST /kick and GET /runs/:id)
- Secret RUNNER_AUTH_TOKEN (Bearer for kind `container`; required outside dry-run)
- Var DRY_RUN = "0" by default; "1" logs intended POST only
- Var GITHUB_OVERRIDE_JOBS = "" (comma-separated job ids that stay on GitHub)

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

## /kick args

`POST /kick` accepts `args` (string values only; anything else is 400
`invalid_args`). They are merged over the row's static inputs with args-win, so
a kick can ADD a key the row does not declare statically — that is how
digithings-cron passes `start_key` for run dedupe.

Each `wd()` row declares `kickArgs`, the keys it accepts. A key that is not on
that list is refused with 400 `kick_arg_not_allowed` and nothing reaches
api.github.com. A row's own static inputs are never on its list: `dry_run`,
`bucket` and `dump_before_prune` are the row's decision, not the caller's. Rows
are never left unbounded, so `kickArgs: []` on a row whose workflow declares no
per-request input is a statement, not a lockout.

To widen a row, add the key to its `kickArgs` in src/jobs.ts. It must be a key
the workflow declares under `on.workflow_dispatch.inputs`; `jobs.test.ts` fails
otherwise, because an undeclared key can only 422. A key the workflow declares
but the row does not own statically may be supplied at any time.

The DIG-55 backfill row also answers 400 `missing_required_arg` on a kick with
no date bound (DIG-369), and that check runs first.

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
