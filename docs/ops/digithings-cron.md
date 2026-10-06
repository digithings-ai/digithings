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
this Worker, including weekly `twelve-x-digisearch-parity` at `8 9 * * MON`
(Mon 09:08 UTC; prior GHA `0 9 * * 1`). Path A traps (`agent-pr-finalizer`,
`agent-backlog-snapshot`, `refresh-repo-activity`, `project-enforce-assignment`)
were restored after #4967 with matching YAML (`workflow_dispatch` only; no
GHA `schedule:`).
Operator full refresh remains manual `workflow_dispatch` / `POST /kick` only.
GHA `schedule:` stays off. Leftover sweep after #4970: develop YAML has
zero `on.schedule` keys (`tests/scripts/test_no_gha_schedules.py`).
`digisearch_parity` is not a digithings workflow.

## Dated snapshot backfill

`POST /backfill` is the Cloudflare-native dispatch path for dated
`fx_confluence_snapshot` remediation in twelve-x. It is deliberately **not** a
`JOBS` row and **not** on a clock: no cron expression, nothing self-firing. It
exists because `jobs.ts` requires a known twelve-x cron for a twelve-x `wd()`
row, and a dated remediation has no such cron — the earlier attempt faked one
with a February 30 expression. Requests POST `{dates: "YYYY-MM-DD,..."}` (plus
optional `force_dates`); every other key is refused, including `run_date`
(which belongs to `daily_run.yml`, not `maintenance.yml` — sending it yields a
silent GitHub `422` and zero runs) and `since`/`until` ranges (unbounded, and
not idempotent per date). A `BackfillLedger` Durable Object makes a repeat POST
for an already-remediated date a no-op with zero upstream requests, and a bare
kick with no `dates` is refused before any request leaves the Worker.

A date is only remediated when GitHub actually starts a run. A dispatch GitHub
declines with a benign 422 — one whose body `isBenign422` matches on `already
queued` or `already running`, in practice a run for the ref already queued —
answers `409 dispatch_suppressed`, records nothing as remediated, and leaves the
date dispatchable, so the next POST retries it instead of reporting a backfill
that never happened. A `disabled_manually` workflow is a different 422 with a
different body (`Cannot trigger a 'workflow_dispatch' on a disabled workflow`),
which is not benign: it answers `502 dispatch_failed`, releases the claim, and
equally records nothing, so the date stays dispatchable. Every response carries a
per-date `states` map, and an in-flight claim ages out after `IN_FLIGHT_TTL_MS`
rather than locking its date out forever.

Off by default (`BACKFILL_ENABLED = "0"`) and gated behind `CRON_KICK_SECRET`.
Full contract, guard ladder and the `disabled_manually` prerequisite are in
[`apps/digithings-cron/README.md`](../../apps/digithings-cron/README.md#snapshot-backfill-post-backfill).
Note that any push touching `apps/digithings-cron/**` deploys this Worker to
production, so a PR against `develop` is a production change.
