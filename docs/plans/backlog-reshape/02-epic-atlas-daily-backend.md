# Epic: Atlas daily-update backend

**Title:** `[Epic] Atlas daily-update backend — price pipeline + scheduler + publish loop`

**Labels:** `epic`, `component:digiquant`, `priority:critical`, `type:feature`

## Goal

Atlas is a **usable, live product**: it ingests prices daily, recomputes its research outputs, and publishes a snapshot that the Atlas frontend (`apps/digiquant-atlas/frontend/`) can render without human intervention. This is the minimum viable "Atlas is running" deliverable and a stated P0 ship item.

Scope is deliberately narrow: **refresh → recompute → publish**. Anything agentic, orchestrated, or multi-agent belongs to a later epic (DigiClaw, ADDM, perf monitor).

## Child tasks

1. **#149** — MIGRATION: Atlas price pipeline → DigiQuant (**in progress**, `task/149-price-pipeline`)
2. **NEW** — Atlas daily pipeline via GitHub Actions cron (draft: `docs/plans/backlog-reshape/01-atlas-daily-cron.md`)
3. **NEW** — Atlas publish step: daily snapshot JSON → frontend-consumable location
4. **NEW** — Atlas frontend wires to daily snapshot (replaces any stubbed/mock data on `apps/digiquant-atlas/frontend/`)
5. **NEW** — Health check + failure alerting for the daily job (GitHub Actions failure → issue comment or Slack webhook)

## Non-goals (explicitly out of scope)

- DigiClaw integration (#173, #216–#221) — deferred to P2
- Multi-user custom research runs — separate epic ("Atlas user profiling")
- Backtesting on demand — separate DigiQuant Phase 1 work (#156, #157)
- Strategy deployment to broker (#181) — Phase 2
- ADDM drift detection (#221) — Phase 2+

## Acceptance

- [ ] A scheduled run on a clean environment fetches prices, recomputes outputs, and publishes the snapshot, without manual intervention, for 3 consecutive trading days.
- [ ] Atlas frontend renders the snapshot (no stubs, no placeholders).
- [ ] Failure mode: if the job fails, a human is notified within one business day.

## Why this epic exists

The priorities stated in the current planning conversation put "Atlas with daily update backend" as the third ship item after digithings.ai and DigiChat. Previously this work was scattered across DigiQuant Phase 1 (#149–#161) and DigiClaw (#173, #218) with no single umbrella; the DigiClaw framing also over-engineered the solution (scheduler service vs. GHA cron). This epic re-scopes to the smallest thing that ships.

## Context

- Tracks to: `frontend/` umbrella plan (ADR-0009), Atlas research-app positioning in `docs/VISION.md`.
- Replaces the "daily" portion of #173 and #218 for the initial ship.
