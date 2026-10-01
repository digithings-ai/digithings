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
(20 expressions after the 2026-10-01 Human Gate pause: DigiQuant pipeline
jobs stay in `src/jobs.ts` with `enabled: false` and are omitted from
wrangler). twelve-x-new-york stays weekday-only on `17 12 * * MON-FRI`.
Resume: set those jobs `enabled: true` and restore wrangler from
`uniqueEnabledCrons()`.

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
session_catchup; keep workflow_dispatch; add header pointing at digithings-cron.

## Jobs

See src/jobs.ts for the full enabled map. market_context uses bucket inputs
intraday / daily / weekly. agent-pr-finalizer dispatches with dry_run=false.
House-run uses repository_dispatch event_type digiquant-baseline (Phase 3).
Price jobs, market-data-refresh, onchain, tearsheets, research-metrics, and
execution-cron-check use `kind: container`. Those four Phase 2 workflows have
no `schedule:` of their own. The runner command catalog is
`apps/digiquant-runner/commands.json`. Operator notes:
`docs/ops/digiquant-runner.md`.
