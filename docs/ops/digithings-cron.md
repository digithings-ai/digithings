# digithings-cron (org production clocks)

Production schedules for digithings-ai no longer rely on GitHub Actions
`on: schedule`. The Cloudflare Worker **digithings-cron** owns the clocks and
dispatches workflows on `ref: main`.

Canonical package + deploy docs:

-> [`frontend/digithings-cron/README.md`](../../frontend/digithings-cron/README.md)

Issue #3579. Default branch stays `develop`; this Worker is the production clock, not a branch flip.
