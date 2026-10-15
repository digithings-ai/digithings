# GHA clocks migration ledger

Status: no GitHub clock remains on `develop`. Every workflow the cutover
de-clocked is clocked by the `digithings-cron` Worker instead.

Measured 2026-10-14 at `develop` = `d227b6ed5`. This document is a record of a
measurement. It is not a runbook.

## What the two guards pin

Two separate facts must both be true after a cutover, and they are pinned in
two different places:

| Fact | Where it is pinned |
|---|---|
| No workflow on `develop` declares `on.schedule` | `tests/scripts/test_no_gha_schedules.py` (#4971, commit `8540d815`) |
| Every de-clocked workflow still has an enabled Worker clock, and its workflow file still exists | `tests/scripts/test_migrated_workflows_still_clocked.py` (DIG-3605) |

The first guard alone is not enough. A `schedule:` block can be removed and the
cutover still looks complete, while the replacement clock in
`apps/digithings-cron/src/jobs.ts` was never added. The second guard is what
turns "port, then disable" into one invariant.

## How to read the table

* **Workflow** — the file in `.github/workflows/` on `develop`.
* **Worker job** — the job id in `apps/digithings-cron/src/jobs.ts` that owns
  the clock. One workflow can own more than one clock.
* **Worker cron** — UTC, fixed. GitHub cron was also UTC, so no offset moved.
* All rows are `workflow_dispatch`-only on GitHub. A human can still start any
  of them by hand.

| Workflow | Worker job | Worker cron |
|---|---|---|
| `agent-backlog-snapshot.yml` | `agent-backlog-snapshot` | `13 6 * * MON` |
| `pipeline-continuous-improvement.yml` | `continuous-improvement` | `8 22 * * SUN` |
| `pipeline-maintenance.yml` | `maintenance` | `8 8 * * MON` |
| `pipeline-provider-review.yml` | `provider-review` | `9 0 * * SUN` |
| `pipeline-dependency-freshness.yml` | `dependency-freshness` | `23 6 * * MON` |
| `refresh-repo-activity.yml` | `refresh-repo-activity` | `10 6 * * MON` |
| `openwiki-update.yml` | `openwiki-update` | `0 8 * * MON` |
| `token-canary.yml` | `token-canary` | `41 6 * * *` |
| `secret-staleness-check.yml` | `secret-staleness` | `17 6 1 * *` |
| `datatap-answer-check.yml` | `datatap-answer-check` | `17 * * * *` |
| `production-deploy-gate-watchdog.yml` | `production-deploy-gate-watchdog` | `17,47 * * * *` |
| `pipeline-checkpoint-archive.yml` | `checkpoint-archive` | `30 13 * * *` |
| `pipeline-market-data-refresh.yml` | `market-data-refresh-morning` | `0 13 * * *` |
| `pipeline-market-data-refresh.yml` | `market-data-refresh-evening` | `30 21 * * *` |
| `pipeline-digiquant.yml` | `house-run-09` | `17 9 * * MON` |
| `project-enforce-assignment.yml` | `project-enforce-assignment` | `23 9 * * *` |

`pipeline-digiquant.yml` also owns `house-run-10`, `house-run-11` and
`house-run-12`, all disabled. That is a deliberate cost decision from
2026-10-01, not a migration gap. The house pattern for a disabled clock is
`{ enabled: false }` on the job row.

## Brief items that are not workflows on `develop`

The cutover request listed four names that do not exist in
`.github/workflows/` on `develop` (64 files):

| Name | Why there is nothing to port |
|---|---|
| `project-status.yml` | Absent from `develop`. |
| `docs-onboard-digithings.yml` | Absent from `develop`. |
| `project-stub-fields.yml` | Absent from `develop`. |
| `deploy-digithings-stack-cloudflare.yml` | Absent from `develop`. The Worker has no lane for it; this is the deploy cutover's own ticket, DIG-3606. |

## Behavioural receipt

Reading `actions/runs?event=schedule` on 2026-10-14:

* The newest scheduled run of any kind on `develop` is
  `OpenWiki Update` at `2026-09-28T16:31:42Z`. Every newer run in the
  `develop` history has a different event.
* The digiquant pipeline stopped running on schedule at 2026-09-04.
* The lifetime `total_count` for that filter reads 2500, which is the API's own
  ceiling for this query. Do not use it as a count. Use `created_at` of the
  newest run, which is the signal above.

So the de-clocking is real, and the clocks that replaced it have been firing
from the Worker since early October.

## Residual: `schedule:` blocks on `main`

`main` still carries four `schedule:` blocks. They cannot fire, because GitHub
reads a schedule from the default branch, and the default branch is `develop`.

* `openwiki-update.yml`
* `pipeline-checkpoint-archive.yml`
* `pipeline-market-data-refresh.yml`
* `production-deploy-gate-watchdog.yml`

These are dead declarations on a non-default branch. They are a latent
double-fire hazard only if `develop` stops being the default branch. This lane
does not change `main`, so it reports them instead of fixing them.

## The Worker's clock table is multi-repo

`jobs.ts` names 48 workflow-targeting rows covering 38 distinct workflow files.
All 38 resolve, and no row dispatches a workflow that no longer exists:

| where the target lives | distinct targets | rows |
| --- | --- | --- |
| `.github/workflows/` in this repository | 24 | 32 |
| `.github/workflows/` in `digithings-ai/twelve-x` | 12 | 14 |
| in-Worker probe, no workflow file expected | 2 | 2 |

The dispatch repository is overridable per row and defaults to `MONOREPO`,
which is `digithings-ai/digithings`. An invariant of the form "every clock
target exists in this repository" is therefore wrong, and the DIG-3605 guard is
scoped to digithings-owned workflows only for that reason.

### The two `smoke-*` rows are the trap in that table

They are `pj()` rows, so `kind: "probe"`, and a probe row runs **inside the
Worker**: `usesGithub()` returns true for a probe row only when its id appears
in `GITHUB_OVERRIDE_JOBS`, which is empty by default. The `workflow` field on
those rows exists so that an override can fall back to a GitHub workflow — the
builder's own docstring says so. `smoke-site.yml` and `smoke-stack.yml` were
deleted from this repository after their last schedule run, which is expected:
the probes still run. **An absent `smoke-*.yml` is not a stale clock.**

## No de-clocked workflow was left without a clock

The inverse direction was audited on 2026-10-15. Every workflow that has ever
produced a `schedule` run in this repository and is still present on `develop`
carries an **enabled** Worker clock: 17 such workflows, 17 clocks, **zero
orphans**. So the migration's "port, then disable" contract holds — no workflow
was de-clocked and left with nothing to fire it.

Method: `GET /repos/digithings-ai/digithings/actions/runs?event=schedule`,
paged, collecting each run's `.path`, then intersected with
`git ls-tree -r github/develop .github/workflows/`. The harvest is a **floor,
not a census** — the API returns 1000 rows against a `total_count` of 2500 — so
a workflow whose only schedule runs predate the window is simply not
represented. That bounds the *absence* claim only: a workflow present in the
harvest provably fired on a schedule, which is the direction the zero-orphan
result rests on. The newest schedule run in the window is `openwiki-update.yml`
at `2026-09-28T16:31:42Z`, the de-clock boundary.

This audit is a measurement, not a pin. `test_migrated_workflows_still_clocked.py`
enforces clock-to-workflow; the workflow-to-clock direction above was checked by
hand and is not asserted by a test.

## Maintenance rule

Re-pointing a clock at another job, disabling one, or renaming one is a
behaviour change. Update
`tests/scripts/test_migrated_workflows_still_clocked.py` and this table in the
same commit that makes it.
