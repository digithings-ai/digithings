# Olympus MVP Daily-Delta — Implementation Plan (historical)

> **⚠️ SUPERSEDED.** Canonical plan: [`2026-06-20-olympus-daily-thesis.md`](./2026-06-20-olympus-daily-thesis.md)  
> Canonical spec: [`2026-06-20-olympus-daily-thesis-design.md`](../specs/2026-06-20-olympus-daily-thesis-design.md)  
> **Tracking:** GitHub **#930** (absorbs #924). Close #924 as merged into #930.

This Jun-19 plan recorded the MVP-delta wave execution. Several tasks **landed** on `task/930-olympus-mvp-delta`; topology tasks (#931 lite, baseline/delta forks) are **abandoned** per the Jun-20 greenfield spec.

## Completed on branch (do not re-implement)

| Task | Issue | Status |
|------|-------|--------|
| ADR-0020 | #930 | ✓ |
| Held-ticker invariant | #936 | ✓ |
| prior_analyst_gaps PM skill | #937 | ✓ |
| PM direction-only + 7E sizer (partial) | #934 | ✓ partial |
| Debate gating | #933 | ✓ (removed in greenfield — H6 replaces 7CD) |
| Context diet | #935 | ✓ |
| Today-only digest | #927 | ✓ |
| Institutional circuit-breaker | #928 | ✓ |
| Alt triage | #929 | ✓ |

## Abandoned / superseded

| Task | Issue | Reason |
|------|-------|--------|
| Hermes lite graph | #931 | Jun-20: single thesis-aware graph, no `OLYMPUS_HERMES_LITE` |
| Baseline vs delta forks | #930 partial | Jun-20: one `daily` cadence + edit-mode per artifact |
| Thesis-first deferred | #924 | Merged into #930 greenfield scope |

## Original plan body

See git history of this file for the full W0–W4 task definitions (forensics reference).
