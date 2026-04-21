# Task: Atlas daily update via GitHub Actions cron

**Title:** `[agent] Atlas daily pipeline — GitHub Actions scheduled run`

**Labels:** `agent-task`, `component:digiquant`, `priority:critical`, `complexity:S`, `type:infra`, `risk:low`

**Component:** digiquant
**Risk:** low
**Execution tier:** cursor
**Model:** sonnet

## Goal

Atlas refreshes its price data and recomputes daily outputs on a fixed schedule without requiring a standing scheduler service. Replaces the DigiClaw cron dependency (#218) for the initial ship. When DigiClaw lands later, this can be migrated — until then, GitHub Actions' `schedule:` trigger is sufficient and reliable.

## Acceptance criteria

- [ ] `.github/workflows/atlas-daily.yml` runs on `schedule: cron '15 6 * * 1-5'` (06:15 UTC weekdays, post-US-close data availability) and on `workflow_dispatch`.
- [ ] Workflow invokes the DigiQuant price pipeline entry point (post #149 migration) against the configured universe and writes outputs to the Atlas storage backend.
- [ ] Workflow publishes a JSON snapshot consumable by `apps/digiquant-atlas/frontend/` (path TBD in acceptance review; default: upload artifact + commit to a `data/` branch or push to object store).
- [ ] Failure notification: workflow fails loudly (non-zero exit) and posts a GitHub issue comment or Slack webhook on failure. Minimal bar: job fails visibly on the Actions tab.
- [ ] Secrets documented: list every env var the workflow needs in `apps/digiquant-atlas/AGENTS.md`.
- [ ] Manual `workflow_dispatch` run succeeds end-to-end before merge.
- [ ] Unit tests pass: `pytest -m unit -k digiquant`.

## Documentation

- `apps/digiquant-atlas/AGENTS.md` — document the daily cron and how to trigger manually.
- `apps/digiquant-atlas/ARCHITECTURE.md` — add a "Daily update" section pointing to the workflow.
- `docs/plans/backlog-reshape/01-atlas-daily-cron.md` — this file, can be removed once issue is filed.

## Context / links

- Parent epic: **"Atlas daily-update backend"** (to be filed alongside).
- Blocked-by: #149 (price pipeline migration into DigiQuant) — currently in-flight on `task/149-price-pipeline`.
- Supersedes (for now): #218 (DigiClaw cron scheduling) — deferred to P3 until DigiClaw is load-bearing.
- Why not DigiClaw: DigiClaw is an OpenClaw-wrapper agent orchestration layer designed for multiple autonomous agents needing drift/perf supervision. Atlas is a single daily job. A scheduler service is a solution looking for a problem until ≥3 recurring agent jobs exist.
