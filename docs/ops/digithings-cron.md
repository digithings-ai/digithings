# digithings-cron (org production clocks)

Production schedules for digithings-ai no longer rely on GitHub Actions
`on: schedule`. The Cloudflare Worker **digithings-cron** owns the clocks and
dispatches workflow runs on the default `develop` branch. Individual workflows
retain their own release and safety gates.

Canonical package + deploy docs:

-> [`frontend/digithings-cron/README.md`](../../frontend/digithings-cron/README.md)

Issue #3579. Default branch stays `develop`; this Worker is the production clock, not a branch flip.

House research/portfolio retries (`house-run-09`…`12`) fire every day (`DOW=*`) with
`refresh_scope=none`. At-open price clocks stay weekday/holiday-sensitive (`MON-FRI` +
ET open gate). Operator full refresh remains manual `workflow_dispatch` only.
