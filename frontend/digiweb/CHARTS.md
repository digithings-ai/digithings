# digiweb charting — the canvas-vs-SVG engine split (#1463)

Two chart engines ship in `@digithings/web`, on purpose, and the split is a
ruling, not an accident:

| Engine | Family | Surfaces | Why |
|---|---|---|---|
| **Canvas** — TradingView Lightweight Charts | `finance-charts` (PriceChart, EquityCurve, DrawdownPlot, `useFinanceChart`/`useLightweightChart` scaffolds) + `finance-composites` (SyncedTearsheet, PerformanceDashboard, …) | **Screen-only dashboards**: olympus observability panes, homepage dashboard composites, anything living behind `rAF` with native crosshair/zoom | Persistent chart lifecycle, native pane sync, cheap incremental updates on live data |
| **SVG** — dependency-free React renderer | `finance-tearsheet` (CandlestickChart, TimeSeries, SignedBars, TradeReturnChart, ReturnsMatrix, KpiStrip, TradeLogTable, TearsheetCard, LiveBadge, `runTearsheetPrint`) | **Print-grade tearsheets**: digiquant `/strategies/*`, olympus performance tear sheet, any surface with a "Download PDF" | The PDF pipeline `flushSync`-re-renders the *same* chart instances at full span and calls `window.print()` — screen and print share ONE render tree. SVG re-renders synchronously and prints crisply; canvas rasterizes and races the print dialog |

## The rule

- A surface that participates in a PDF/print export composes the
  **finance-tearsheet** family. Canvas is disqualifying there — this is a hard
  constraint, not a preference (see
  [digiquant's ruling](../digiquant-web/components/tearsheet/CHARTS.md) and
  [olympus' ruling](../olympus/lib/CHARTS.md), both upheld through the F2/F4
  adoption passes).
- A screen-only dashboard composes **finance-charts / finance-composites**.
  Do not rebuild zoom/pan/crosshair in SVG for a surface that never prints —
  the canvas engine does it natively.
- One surface, one engine. If a preview and a full view show the same data
  (digiquant's homepage cards + tearsheet price pane), they share the SVG
  engine rather than forking per surface.

## What the SVG family expresses that canvas does not

External `ViewWindow` control synced across charts + lookback-preset
matching, trade entry/exit markers with hover cards, linear/log/symlog
scales, the unrealized open-leg bar state, and the entire unlayered
`@media print` grammar in `styles/finance-tearsheet.css` (light-token pins,
`[hidden]` pane opening, break-inside rules). These were the recorded gaps
that made tearsheets keep local renderers before #1463 promoted the grammar.

## Interaction with the matrix

`ReturnsMatrix` (finance-tearsheet) is THE period-matrix grammar — 3 metrics
× 3 granularities, data-driven max-abs tint, signed compact %, compounded
Year column. The old `MonthlyReturns` heatmap (finance-charts) was deprecated
into it in #1463; do not reintroduce a second matrix.

## Live catalog

`/finance` (reference app, port 4013) shows the canvas family, including the
screen-only SyncedTearsheet composite; `/tearsheet` shows the SVG family
end-to-end, including a working Download PDF export.
