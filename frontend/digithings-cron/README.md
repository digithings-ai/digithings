# digithings-cron

Org-wide Cloudflare Worker that owns production clocks for digithings-ai (#3579).

Replaces unreliable GitHub Actions schedule triggers with Cloudflare Cron Triggers
that dispatch workflow_dispatch / repository_dispatch against ref main on
digithings-ai/digithings and digithings-ai/twelve-x (FX Hub).

Thin Worker only — no Containers / Durable Objects. Default branch stays develop.

## Layout

- wrangler.toml — name digithings-cron, triggers crons, DRY_RUN var
- src/jobs.ts — typed job map
- src/dispatch.ts — GitHub API dispatch (204/200 ok; 422 already-running = success)
- src/et-open.ts — America/New_York >= 09:30 gate
- src/index.ts — scheduled + GET /healthz + optional POST /kick

## Env

- Secret GH_DISPATCH_TOKEN (required for real dispatch)
- Optional secret CRON_KICK_SECRET (enables POST /kick)
- Var DRY_RUN = "0" by default; "1" logs intended POST only

Set secrets from this directory with wrangler secret put (never echo values).

## Unique crons

33 unique cron expressions in wrangler.toml [triggers]. Cron `17 12 * * 1-5` fires
both digithings house-run-12 and twelve-x-new-york.

## Local

```
cd frontend/digithings-cron
npm install && npm test && npm run typecheck
npm run dev
# curl http://127.0.0.1:8787/__scheduled?cron=...
```

## Deploy

Deploy from main only. CI workflow: .github/workflows/deploy-digithings-cron.yml
(push paths frontend/digithings-cron/** + workflow_dispatch; Node 22; wrangler deploy).
Needs CLOUDFLARE_API_TOKEN + CLOUDFLARE_ACCOUNT_ID. GH_DISPATCH_TOKEN is set once
manually on the Worker, not from deploy logs.

## Migration

digithings: schedule blocks removed in this PR, workflow_dispatch / repository_dispatch kept.

twelve-x follow-up (other repo): remove schedule from daily_run_asia/london/new_york,
market_context_ingest (keep bucket input), performance_eval, primemarket_session_heartbeat,
session_catchup; keep workflow_dispatch; add header pointing at digithings-cron.

## Jobs

See src/jobs.ts for the full enabled map. market_context uses bucket inputs
intraday / daily / weekly. agent-pr-finalizer dispatches with dry_run=false.
House-run uses repository_dispatch event_type olympus-daily (leftover id only).
