# Olympus chart inventory & engine ruling (#1420, epic #1414)

> **Ruling: lightweight-charts is the canon for time-series; recharts is
> sanctioned for categorical/composition surfaces (lightweight-charts has no
> categorical grammar).**

The reference grammar for lightweight-charts lives in the digiweb design
reference (`frontend/digiweb/reference/components/equity-curve-reference.tsx`,
`drawdown-plot-reference.tsx`): token-themed via CSS-variable reads with SSR
fallbacks, `autoSize: true`, no custom candle renderers. Since #1450 batch E
the scaffold itself lives in `@digithings/web` (the finance-charts family's
`lw-chart.tsx`: persistent `useLightweightChart` lifecycle with `isAlive()`
disposal guard, `toLineData`/`timeToISO` adapters, `useChartTip`/
`ChartTipShell` tooltip plumbing, `chartChromeOptions` token chrome shared
with `useFinanceChart`); `lib/lw-chart.tsx` here is a thin adapter binding
that scaffold to olympus's ChartColors — every color continues to come from
`lib/chart-colors.ts` (the single sanctioned color source, #1402), which
stays olympus-local (fixed categorical/benchmark hues are app vocabulary,
not package surface).

## Classification

TIME-SERIES = the x-axis is trading time (NAV/equity curves, price charts,
drawdown area, rolling metrics, comparable NAV). Everything else (bars keyed by
ticker/bucket/leg, stacked composition, trivial sparklines) stays on recharts.

### Migrated to lightweight-charts

| File | Chart(s) | Why it is time-series |
|---|---|---|
| `components/portfolio/performance-chart-workspace.tsx` | `NavComparableChart` (indexed NAV area + dashed comparable overlays), `DailyReturnsComboChart` (daily-% histogram + NAV-index line), drawdown view = shared `<SyncedTearsheet/>` (`@digithings/web`, #1548: one instance, NAV pane over underwater pane, shared axis/crosshair/zoom) | The canonical equity-curve surface: daily NAV vs benchmark tickers; daily returns are per-trading-day values on the same axis. |
| `components/portfolio/performance-rolling-chart.tsx` | Rolling Sharpe + rolling ann. vol (dual price scale) | Rolling risk metrics over a trading-day window. |
| `components/portfolio/PositionDrilldown.tsx` | Weight-% area + close-$ line (dual scale) with event dots; cumulative-ppt mini pane | Both panes are daily series over the drilldown window. |

The standalone `components/portfolio/performance-drawdown-chart.tsx`
(underwater BaselineSeries mirroring `drawdown-plot-reference.tsx`) was
**deleted in #1548**: the workspace's Drawdown view now renders the shared
`<SyncedTearsheet/>` — same underwater grammar (BaselineSeries under 0, --down
fills), plus the NAV pane above it on the same time axis. The shipped
drawdown numbers are preserved by passing `buildDrawdownSeries` output
explicitly (the primitive's own peak-derived series rounds to one decimal).
Deltas accepted with the adoption: the primitive uses the native
lightweight-charts crosshair (axis labels) instead of the app's
`ChartTipShell` HTML tooltip, and its drawdown pane has no `%`-suffixed
priceFormat.

### Stays on recharts (sanctioned)

| File | Chart(s) | Why it stays |
|---|---|---|
| `components/portfolio/sleeve-stacked-chart.tsx` | 100%-stacked sleeve allocation area (+ click-to-select date) | Composition over time — lightweight-charts has no stacking grammar. |
| `components/observability/AttributionTab.tsx` | Contribution by position bars | Categorical (x = ticker). |
| `components/observability/DecisionScorecardTab.tsx` | Hit-rate by conviction bucket bars | Categorical (x = conviction bucket). |
| `components/twelve-x/ConsensusTab.tsx` | Consensus score lines (x = run_date) + position-split stacked area | The stacked split is composition (no lw grammar) and both panes share one currency-selection/smoothing state; splitting one view across two engines costs more than canon buys. Honest note: the score-lines pane *is* time-indexed — if it is ever decoupled from the split pane it becomes a migrate candidate. |

`components/tearsheet/OlympusTearsheetView.tsx` renders the shared
finance-tearsheet family's print-oriented SVG charts (`TimeSeries`,
`SignedBars` from `@digithings/web`, #1463) and is out of scope for both
engines here — print-grade surfaces are pure SVG by hard constraint (the PDF
pipeline re-renders them via `runTearsheetPrint`); the canvas-vs-SVG split
ruling lives in `frontend/digiweb/CHARTS.md`.

## Promotion gap ledger (#1548 adoptions)

Where a shared primitive could not express shipped behavior, the rich path
stayed local and the gap is recorded here as the promotion spec (MIGRATION.md
"Promotion playbook v2": never force a primitive; ledger the gap).

- **`<SyncedTearsheet/>` vs the NAV-comparables view** (SCOPED adoption).
  The primitive hosts the workspace's Drawdown view only. The NAV view
  (`NavComparableChart`) and Daily-returns view stay local because the
  primitive cannot express, in order of weight:
  1. **Overlay series** — N dashed comparable `LineSeries` on the equity
     pane, colored per ticker from `lib/chart-colors.ts` (app vocabulary),
     with a legend whose entries *remove* an overlay. Promotion spec: an
     optional `series?: { id: string; points: TearsheetPoint[]; color?:
     string; dashed?: boolean }[]` prop rendered into pane 0, plus a legend
     slot or `onSeriesRemove` callback.
  2. **Custom crosshair tooltip** — the app's `useChartTip`/`ChartTipShell`
     HTML tooltip (per-date rows for portfolio + every overlay + activity
     events). Promotion spec: expose the chart/crosshair via a render-prop
     or `onCrosshairMove` surface instead of the baked `aria` host.
  3. **Series markers** — activity-event dots (`createSeriesMarkers`) on the
     NAV series.
  4. **Visible-range / range-switch control** — today range switching swaps
     the data arrays (the primitive rebuilds + `fitContent()`, which is
     enough), but a controlled `visibleRange` prop would be needed the day
     the workspace zooms without re-fetching.
  5. **Per-pane priceFormat** — the drawdown pane wants a `%` suffix, NAV a
     2-dp custom formatter.
- **`<TagsInput/>` (full field) vs the NAV-comparables picker** (composed
  parts instead). The picker's chips live *outside* the dropdown pane while
  the filter input lives *inside* it; selection is constrained to the
  ticker-universe listbox (no free-text commit — TagsInput's Enter/comma
  commit and Backspace-removes-last-chip semantics are wrong here); the cap
  (`MAX_COMPARABLES`) gates adds at the listbox. So the adoption composes
  the promoted `<TagChip/>` (dress `tg-chip-quant`) and `<SearchBar/>`
  (dress `ctl-search-row`) from `@digithings/web` and keeps the trigger,
  pane, outside-click dismissal and capped listbox caller-side. Accepted
  micro-delta: TagChip's × is an 11px stroke SVG (was a text `×`);
  SearchBar's clear affordance replaces the native WebKit search-cancel.
- **`<PerformanceDashboard/>` ← server-metrics strip** (FULL adoption,
  sanctioned look change). The inline `qn-metric` strip on the Performance
  tab's Diagnostics card moved onto the canonical dashboard grammar
  (headline = server P&L, toned; ratio strip = sharpe / ann. vol / max
  drawdown / cash / invested; allocation bars = latest-date category slice
  of `buildSleeveStackSeries(position_history)` — no new fetch). The
  strip's "Server metrics · date · generated" caption folds into the
  headline label + note; nothing else was dropped. Long sleeve labels
  ("Intermediate Duration") wrap inside the primitive's fixed 6rem name
  column — cosmetic only. **Wiring dependency**: `app/globals.css` must
  `@import "@digithings/web/styles/finance-composites.css"` and
  `@source "../../digiweb/web/src/components/finance-composites";`
  (pdash-* hairlines + the component's token utilities).

## Grammar for new charts

- New **time-series** chart → `useLightweightChart` from `lib/lw-chart.tsx`
  (token theming, autoSize, theme-reactive re-skin, reduced-motion handling
  come for free — the lifecycle itself is the shared `@digithings/web`
  finance-charts scaffold). Colors only from `lib/chart-colors.ts`.
- New **categorical/composition** chart → recharts, colors only from
  `lib/chart-colors.ts` (`useChartColors()` for semantic hues, the fixed
  allowlist for series identity).

Guarded by `lib/lw-chart-canon.test.ts` and `scripts/check_frontend_canon.py`.
