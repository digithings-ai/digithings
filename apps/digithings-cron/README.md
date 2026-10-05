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
- src/required-triggers.ts — the crons the FX pipeline requires, and why
- src/trigger-contract.ts — pure contract evaluation, two alarm classes
- src/trigger-alarm.ts — raises the twelve-x issue for a broken contract
- src/deployed-triggers.ts — reads the deployed schedule from the Cloudflare API
- src/wrangler-config.ts — reads/rewrites wrangler.toml text for the gate
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
(38 expressions after twelve-x digisearch parity). House-run is
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

## Required trigger contract (DIG-732)

`src/required-triggers.ts` is the contract as data: every cron the FX pipeline
needs, with the reason it is required and what is lost without it. Today that is
the three session clocks, `twelve-x-session-catchup`, and
`twelve-x-primemarket-heartbeat`. Each row names the capability, so DIG-678 /
DIG-55 may change which job fills a row but may never let a required cron vanish
silently.

DIG-553 Finding 1 (measured over 543 runs): 1–30 Aug 2026 had zero catch-up runs,
so every failed day auto-unrecovered, and six client-visible stale days (7, 14,
19, 20, 24, 25 Aug) predated the Worker's first clock day on 2026-08-31 and were
unrecoverable. Deleting the `twelve-x-session-catchup` job row and its cron line
together left `src/jobs.ts`'s own assertion green — only a copied id list in a
unit test noticed, and nobody ran it for five weeks.

Two distinct alarm classes, one issue per occurrence, the label is the class
(twelve-x convention, `tests/test_alerting_workflows.py` in twelve-x):

- `missing_required_cron` — a required cron is absent from the trigger list under
  test, or its job row is gone, disabled, or points at a different cron. Label
  `cron-missing-required-trigger`.
- `unrecognised_cron` — a cron fires and maps to no enabled job, so it starts
  nothing. Label `cron-unrecognised-trigger`. This is not the same failure as a
  missing required cron and must not read as one. Raised from the cron tick in
  `src/index.ts` (scheduled only; a human typing a cron on POST /kick is not drift).

A broken contract opens an issue in `digithings-ai/twelve-x` through
`GH_DISPATCH_TOKEN` and never throws. Absence is loud by default: an unmet
contract fails the deploy and alarms.

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

Two gate layers, because a contract satisfied by the repo but not by the
deployment is Finding 1 wearing a passing test:

1. "Test + typecheck" runs `npm run test --workspace digithings-cron`, which
   includes `src/trigger-contract.test.ts` checking the contract against
   `wrangler.toml` `[triggers].crons`. A merge that deletes a required job row
   and its cron line together fails here and never reaches the deploy.
2. After Deploy, "Verify the deployed trigger contract" runs
   `npm run check:deployed-triggers --workspace digithings-cron`, which reads the
   live schedule via `GET /accounts/{account_id}/workers/scripts/{script}/schedules`
   and asserts the contract against it, retrying while schedules propagate. It
   needs `REQUIRE_DEPLOYED_CONTRACT=1` to be mandatory (it is, in CI), plus
   CLOUDFLARE_API_TOKEN, CLOUDFLARE_ACCOUNT_ID and GH_DISPATCH_TOKEN for the alarm.
   Without a token on a laptop it prints `[deployed contract] NOT VERIFIED` and skips.

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
