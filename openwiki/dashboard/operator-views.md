---
type: frontend-guide
title: Dashboard Operator Views
description: Operator views of the digiquant dashboard — research, portfolio, tearsheet, ledger, attribution — with house book scope and fail-closed P&L.
tags: [dashboard, digiquant, portfolio, tearsheet, ledger]
sources:
  - id: openwiki-source-3642bf77f250aaf3ce57767a
    resource: repo://frontend/dashboard/lib/accounting-views.ts
  - id: openwiki-source-e6525599bfc8bec8757a3caa
    resource: repo://frontend/dashboard/lib/house-workspace.test.ts
  - id: openwiki-source-c59f4d4f9b9754e31fe404ca
    resource: repo://frontend/dashboard/lib/house-workspace.ts
  - id: openwiki-source-4b479ed8d11ca62135d6071d
    resource: repo://frontend/dashboard/README.md
generated: { by: "opencode", at: "2026-09-07T22:38:58.074Z" }
verified:
  - by: openwiki/0.5.0
    at: 2026-09-09T14:37:17.158Z
---

# Dashboard Operator Views

The dashboard renders persisted research and portfolio state. Its views
share two invariants: **house book scope** (Group A reads go through
`houseBook()` so overlay weights never seed the public book) and
**fail-closed P&L** (missing basis or mark renders `—`; the UI never
invents numbers).

## Research and portfolio

`app/research/` and `app/portfolio/` present daily research documents
(theses, briefs) and the portfolio book (holdings, performance, ledger,
attribution, tickers). Research views link published documents to the
positions they motivated via brief-book events; portfolio views read the
house book only.

## Performance tearsheet

`app/portfolio/performance/` renders the finance-tearsheet view: persisted
NAV and return metrics, a base-zero portfolio path, current-book
contribution, and open-position outcomes. It prefers stored
`unrealized_pnl_pct` / `since_entry_return_pct`, else derives from
`entry_price` vs `current_price`, filling a missing nightly mark from
`price_history` (stamped with that close date). Benchmark comparison
defaults to SPY, aligning the benchmark universe from `price_history` to
the NAV dates and recomputing excess return (Rp − Rb) on change.

## Ledger

`app/portfolio/ledger/` is the single source of truth for fills: every
`OPEN` / `ADD` / `EXIT` / `TRIM` event with average entry, fill price, and
realized % vs average entry for sells. The tearsheet links here instead of
duplicating a closed-positions tab. `position_events`
`cumulative_return_since_event_pct` is post-event drift, never presented as
trade return.

## Attribution

`app/portfolio/attribution/` defaults to a compact decision-effectiveness
monitor with book attribution and audit as sibling views. Headline metrics
use direction-adjusted alpha over independently scored decisions;
calibration stays "insufficient evidence" until at least two buckets each
hold 10 independent decisions. Audit preserves every raw row at 25 rows per
page.

## House book scope

Every house-dashboard Group A read (`positions`, `nav_history`,
`position_events`, `portfolio_metrics`) goes through `houseBook()`, which
pins the house `workspace_id` — omitted workspace filters would mix
overlay rows into the public book. Shared teasers without `workspace_id`
(`daily_snapshots`, `theses`, `instruments`) stay date-only, and accounting
NAV reads the `public_accounting_nav_history` view (finalized tips plus
labeled legacy estimates, with rollback to legacy views by repointing
constants).
