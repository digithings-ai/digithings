# Dashboard table inventory & SortableTable ruling (#1450 F4 batch D + F5 tables, epic #1414)

> **Ruling: the promoted `<SortableTable/>` leaderboard (`@digithings/web`
> finance-composites) is NOT adopted for the dashboard portfolio tables or the
> twelve-x tables.** Every batch-D and F5-tables target either has no tabular
> render or is built around interactions the primitive's grammar cannot host.
> Local code stays, per the migrate-vs-leave / honest-engineering contract
> (`frontend/digiweb/MIGRATION.md`, promotion playbook step 3 — the
> `lib/CHARTS.md` engine ruling is the in-app precedent).

## What the primitive offers

`SortableTable` (`frontend/digiweb/web/src/components/finance-composites/SortableTable.tsx`)
is a **flat, always-sorted leaderboard**: real `<button>` headers with
`aria-sort` (keyboard-accessible sort), numeric vs lexical comparison,
string-only cells via `format`, **column-scoped** money tone (`up`/`down`
for the whole column), and the mono `srt-*` grammar from
`styles/finance-composites.css`. It has no row interaction, no grouping, no
per-column responsive visibility, and no "natural order" state — it sorts on
mount by the first column (or `defaultSort`) unconditionally.

## Per-file inventory (batch-D targets)

| File | Surface | Why it keeps local code |
|---|---|---|
| `components/portfolio/AllocationsPositionsTable.tsx` | Allocations tab positions table | Sector **group header rows** (`colSpan` subtotal rows interleaved with position rows) are the primary structure — a flat sort by any column would tear the grouping apart, and the shipped order (conviction-desc within sector, sectors by weight) is deliberately fixed, not user-sortable. Cells are ReactNode (ConvictionMeter, RiskEnvelopeCell, weight bar scaled to the max weight, `SignedConvictionBadge` deep-link with `stopPropagation`) where the primitive's `format` returns strings; Target/Δ columns are conditional (`hasTargets`); 9 columns hide responsively (`hidden md/lg/xl:table-cell`). |

The Performance tab's two batch-D rows — `position-pnl-table.tsx` (P&L table,
same row-drilldown grammar) and `advanced-stats-panel.tsx` (a `MetricCard` KPI
grid, never a table) — were **deleted in #1747** along with the rest of the
orphaned tab, as was the `PositionDrilldown` row-expansion this section's
Allocations row used to share with them.

## Per-file inventory (F5 twelve-x targets, #1450 F5 tables)

| File | Surface | Why it keeps local code |
|---|---|---|
| `components/twelve-x/ConsensusDataTable.tsx` | Consensus — G10 table | A **frozen visual spec** whose grammar exceeds the primitive's string-cell API on six axes: **ReactNode cells** in 4 of 9 columns (the divergent `ConsensusScoreBar`, `DeltaChip` with new-currency state, `currencyColor`-styled ticker, optional per-row "Why?" provenance cross-link) where `format` returns strings; **per-cell conditional color** (`scoreColorClass` / vs-Avg arrow classes vary per row — the primitive's `tone` is column-scoped); a **non-sortable presentational column** (the score bar — every `SortableTable` header is a sort button); **derived sort values** (vs-Avg sorts by the score−avg gap, not the cell field) with **null-last ordering in both directions**, pinned by `ConsensusDataTable.test.tsx` (the primitive `String(null)`-compares); the optional **Trace column** keyed off `onDrillToProvenance`; and the deliberately unlayered `.srt-table td` dress (`finance-composites.css`), which would override the frozen spec's per-column typography from underneath call-site utilities. The local table already carries the primitive's accessibility grammar — real `<button>` headers (keyboard sort) and `aria-sort` on `<th>`. Partial adoption is structurally impossible: `SortableTable` is a whole-table component, not a headless sort hook. |
| `components/twelve-x/MatrixTab.tsx` | Broker-by-currency matrix | **No sortable tabular surface exists in the file** (no sort state anywhere) — its only table-like structure is the broker-by-currency ARIA grid (CSS grid with sticky rowheaders and conviction-shaded cell buttons), which stays a custom render by design. |

## What adoption would take (if a product ruling ever wants these sortable)

Recorded so a future promotion pass can size the gap instead of re-auditing:

- `format` widened from `string` to `ReactNode` (backward-compatible type
  change) — hosts ConvictionMeter / SignedConvictionBadge / RiskEnvelopeCell
  cells.
- Per-column `className` on `<th>`/`<td>` — hosts the responsive
  `hidden md:table-cell` visibility the dashboards rely on.
- Per-cell tone (e.g. `tone` as `(value, row) => "up" | "down" | undefined`) —
  hosts sign-dependent money colors.
- An unsorted "natural order" state (or controlled sort) — required to keep
  today's initial row order.
- Sort-value accessors (sort by a derived value, not the cell field) with
  null-last semantics in both directions — hosts ConsensusDataTable's vs-Avg
  gap sort.
- Per-column `sortable: false` — hosts presentational columns (score bar).
- A dress axis (opt out of / re-skin the unlayered `.srt-table td`
  typography) — required wherever a frozen visual spec sets per-column type.
- Row expansion (`renderDetail` + row click) — the drilldown named in the
  batch brief as the canonical cannot-host example; a deliberate non-goal for
  a leaderboard primitive.
- Group header rows — out of scope entirely; a grouped table is a different
  primitive, not a leaderboard variant.

## Grammar for new tables

A new **flat, read-only leaderboard** (rank-by-column, no row interaction,
uniform column tones) should adopt `<SortableTable/>` from `@digithings/web`
instead of hand-rolling sort state — wire
`@import "@digithings/web/styles/finance-composites.css"` (plain, no
`layer(…)` — it manages its own layering) plus the matching `@source` line
per `MIGRATION.md`. Tables with row interaction, grouping, or mixed-tone
cells stay local until the gaps above are promoted.

---

## Performance SSOT (#3580)

One contracted series and one committed-book date across Brief, Tearsheet,
Ledger, and Portfolio. Live marks on Brief are a **badged overlay** only —
never a silent second truth.

| Concern | Canonical source | Notes |
|---|---|---|
| **NAV chart** | `public_accounting_nav_history` (`ACCOUNTING_NAV_VIEW`) | Fail closed on query error (#3029). Tip contract badge: `finalized_accounting` vs `legacy_estimate`. |
| **Headline returns** | Same accounting NAV tip via shared pure helpers (`persistedHeadlinesFromNav` / `buildPerformanceTearsheet`); Tearsheet loads through `getPerformanceBundle` | Brief without live overlay must match Tearsheet within 0.05 pp. Brief rebuilds from dashboard snapshots of the same view (not a second fetch). |
| **Invested %** | Accounting NAV tip `invested_pct` | Fallback: book weights → `portfolio_metrics.invested_pct`. Never mix live weights with book weights silently. |
| **Book as-of date** | `committedBookDate(daily_snapshots.date, positions.date)` | Portfolio / Ledger / Brief book chrome. Do not imply marks refreshed when `metrics_as_of` is null. |
| **Ledger events** | `position_events` (house book) | Session day on Brief; full stream on Ledger. |
| **Persisted risk KPIs** | `portfolio_metrics` | Lag badge when `metrics.as_of` / `date` trails NAV tip by ≥1 day. Pipeline writers: `finalize_period_accounting` + `refresh_performance_metrics` (see #3563 / #3467 for `main` lock unblock). |

Code entrypoints:

- `frontend/dashboard/lib/performance-ssot.ts` — pure SSOT helpers
- `frontend/dashboard/lib/observability-queries.ts` — `getPerformanceBundle()` (Tearsheet + shared builder)
- `frontend/dashboard/app/page.tsx` — Brief persisted path + live-marks badge
- `frontend/dashboard/app/portfolio/performance/page.tsx` — Tearsheet consumer
