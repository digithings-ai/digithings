# digithings-cron (org production clocks)

Production schedules for digithings-ai no longer rely on GitHub Actions
`on: schedule`. The Cloudflare Worker **digithings-cron** owns the clocks and
dispatches workflow runs on the default `develop` branch. Price and
market-data jobs POST the private digiquant-runner instead
([digiquant-runner.md](digiquant-runner.md), #4761). Individual workflows
retain their own release and safety gates.

Canonical package + deploy docs:

-> [`apps/digithings-cron/README.md`](../../apps/digithings-cron/README.md)

The dispatched pipelines' shared Postgres secret is documented in
[`core-postgres-uri-secret.md`](core-postgres-uri-secret.md) (#3979).

Issue #3579. Default branch stays `develop`; this Worker is the production clock, not a branch flip.

House research/portfolio runs once a week (`house-run-09` at `17 9 * * MON`,
cost lock 2026-10-01) with `refresh_scope=none`. Daily `house-run-10/11/12`
retries stay disabled. Research + dashboard/portfolio stay fed by the other
enabled DigiQuant clocks (prices, market-data, metrics, tearsheets, onchain).
At-open price clocks stay weekday/holiday-sensitive (`MON-FRI` + ET open gate).
twelve-x FX Hub clocks (`twelve-x-*`) are live `workflow_dispatch` jobs on
this Worker. Dead Path A trap rows (agent/project/refresh) were dropped from
the job map; their YAML was deleted in #4919 and is not restored.
Operator full refresh remains manual `workflow_dispatch` / `POST /kick` only.
GHA `schedule:` stays off.
