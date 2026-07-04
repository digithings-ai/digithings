## Goal

Add optional **Olympus footer status dot** wired to DigiSmith `GET /v1/status` — Graphite-style operator health indicator for dashboard surfaces ([design spec §Layer B](../../../superpowers/specs/2026-06-30-frontend-design-evolution-layers-design.md)).

## Component

- [x] `frontend/olympus/`

## Acceptance Criteria

- [ ] Small status dot in Olympus footer (or app shell) — green/amber/red mapped from DigiSmith diagnostic response
- [ ] Poll interval documented (e.g. 60s); graceful degradation when DigiSmith unreachable (grey/unknown)
- [ ] No PII in tooltip; optional mono label "all systems operational" / "degraded"
- [ ] Does not block page load; fetch is async/non-blocking
- [ ] Feature flag or env to disable in local dev without stack
- [ ] Document in Olympus ARCHITECTURE.md

## Test Requirements

- Manual with stack-local: dot reflects `/v1/status`
- Manual without DigiSmith: dot shows unknown state, no console errors
- Olympus build passes

## Documentation to Update

- [ ] `frontend/olympus/ARCHITECTURE.md`
- [ ] `frontend/design/EVOLUTION.md`

## Out of Scope

- Load balancer health probes (use `/healthz` on services)
- Alerting/paging integration

## Dependencies

- Blocked by: #1216 (glass→surface footer chrome)
- Unblocks: none

## Human Gate Required?

- [ ] No

## Priority

P3 — optional operator polish.
