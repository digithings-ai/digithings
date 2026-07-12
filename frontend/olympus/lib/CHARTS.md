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
| `components/portfolio/performance-chart-workspace.tsx` | `NavComparableChart` (indexed NAV area + dashed comparable overlays), `DailyReturnsComboChart` (daily-% histogram + NAV-index line) | The canonical equity-curve surface: daily NAV vs benchmark tickers; daily returns are per-trading-day values on the same axis. |
| `components/portfolio/performance-drawdown-chart.tsx` | Underwater drawdown area | Peak-to-trough % over trading days — direct mirror of `drawdown-plot-reference.tsx` (BaselineSeries). |
| `components/portfolio/performance-rolling-chart.tsx` | Rolling Sharpe + rolling ann. vol (dual price scale) | Rolling risk metrics over a trading-day window. |
| `components/portfolio/PositionPriceChart.tsx` | Daily close area + OPEN/EXIT/ADD/TRIM markers + entry guide | A price chart — lightweight-charts' home turf; native pan/zoom replaces the hand-rolled recharts brush + wheel handler. |
| `components/portfolio/PositionContributionChart.tsx` | Cumulative contribution-to-NAV (ppt) area + activity markers | Daily cumulative attribution series (same pane grammar as the price chart). |
| `components/portfolio/PositionDrilldown.tsx` | Weight-% area + close-$ line (dual scale) with event dots; cumulative-ppt mini pane | Both panes are daily series over the drilldown window. |

### Stays on recharts (sanctioned)

| File | Chart(s) | Why it stays |
|---|---|---|
| `components/portfolio/sleeve-stacked-chart.tsx` | 100%-stacked sleeve allocation area (+ click-to-select date) | Composition over time — lightweight-charts has no stacking grammar. |
| `components/portfolio/PositionContributionEventBars.tsx` | "Δ ppt between activity dates" horizontal bars (extracted from `PositionContributionChart.tsx`) | Categorical: one bar per activity leg (labelled by event), not per day. |
| `components/portfolio/nav-sparkline.tsx` | Axis-less NAV sparkline (overview tile) | Trivial sparkline carve-out — no axes, grid, or tooltip; nothing for lightweight-charts to add. |
| `components/observability/AttributionTab.tsx` | Contribution by position bars | Categorical (x = ticker). |
| `components/observability/DecisionScorecardTab.tsx` | Hit-rate by conviction bucket bars | Categorical (x = conviction bucket). |
| `components/twelve-x/ConsensusTab.tsx` | Consensus score lines (x = run_date) + position-split stacked area | The stacked split is composition (no lw grammar) and both panes share one currency-selection/smoothing state; splitting one view across two engines costs more than canon buys. Honest note: the score-lines pane *is* time-indexed — if it is ever decoupled from the split pane it becomes a migrate candidate. |

`components/tearsheet/OlympusTearsheetView.tsx` renders the shared
finance-tearsheet family's print-oriented SVG charts (`TimeSeries`,
`SignedBars` from `@digithings/web`, #1463) and is out of scope for both
engines here — print-grade surfaces are pure SVG by hard constraint (the PDF
pipeline re-renders them via `runTearsheetPrint`); the canvas-vs-SVG split
ruling lives in `frontend/digiweb/CHARTS.md`.

## Grammar for new charts

- New **time-series** chart → `useLightweightChart` from `lib/lw-chart.tsx`
  (token theming, autoSize, theme-reactive re-skin, reduced-motion handling
  come for free — the lifecycle itself is the shared `@digithings/web`
  finance-charts scaffold). Colors only from `lib/chart-colors.ts`.
- New **categorical/composition** chart → recharts, colors only from
  `lib/chart-colors.ts` (`useChartColors()` for semantic hues, the fixed
  allowlist for series identity).

Guarded by `lib/lw-chart-canon.test.ts` and `scripts/check_frontend_canon.py`.
