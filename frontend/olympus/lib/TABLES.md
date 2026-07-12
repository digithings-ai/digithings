# Olympus table inventory & SortableTable ruling (#1450 F4 batch D + F5 tables, epic #1414)

> **Ruling: the promoted `<SortableTable/>` leaderboard (`@digithings/web`
> finance-composites) is NOT adopted for the olympus portfolio tables or the
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
| `components/portfolio/AllocationsPositionsTable.tsx` | Allocations tab positions table | Sector **group header rows** (`colSpan` subtotal rows interleaved with position rows) are the primary structure — a flat sort by any column would tear the grouping apart, and the shipped order (conviction-desc within sector, sectors by weight) is deliberately fixed, not user-sortable. Rows **click-to-expand** into a `PositionDrilldown` `<tr colSpan>`; cells are ReactNode (ConvictionMeter, RiskEnvelopeCell, weight bar scaled to the max weight, `SignedConvictionBadge` deep-link with `stopPropagation`) where the primitive's `format` returns strings; Target/Δ columns are conditional (`hasTargets`); 9 columns hide responsively (`hidden md/lg/xl:table-cell`). |
| `components/portfolio/position-pnl-table.tsx` | Performance tab P&L table | Same row **drilldown** — and it is always live: the only call site (`PerformanceTab`) always derives `priceChartAnchorDate` (last snap date, else `meta.last_updated`). P&L % wears **per-cell sign-dependent** `text-up`/`text-down` (the primitive's `tone` is column-scoped); 3 columns hide responsively; and the primitive's unconditional initial sort would reorder rows away from today's API order (including the CASH row's position). |
| `components/portfolio/advanced-stats-panel.tsx` | Performance tab advanced statistics | **Not a table at all** — a `MetricCard` KPI grid (`grid grid-cols-2 md:grid-cols-4`) over locally computed stats. There is no column/sort grammar to re-back. |

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
