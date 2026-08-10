# digiquant tearsheet — chart & table engine ruling (#1450 F2, adopted #1463)

> **Ruling: tearsheet surfaces are print-first pure SVG and now ride the
> promoted `@digithings/web` finance-tearsheet family. The canvas finance
> family (finance-charts / finance-composites — TradingView Lightweight
> Charts) is NOT adopted on any tearsheet surface.** The engine split is
> canon: see [frontend/digiweb/CHARTS.md](../../../digiweb/CHARTS.md) —
> canvas for screen-only dashboards, SVG finance-tearsheet for anything that
> participates in a PDF export.

## Why SVG is a hard constraint here

**Every chart surface participates in the PDF export.** "Download PDF"
(`runTearsheetPrint`, `@digithings/web`) `flushSync`-re-renders the *same*
chart component instances at full span (`PRINT_FULL_VIEW`, linear scale) and
then calls `window.print()`; the family print grammar
(`@digithings/web/styles/finance-tearsheet.css`, imported in
[`app/globals.css`](../../app/globals.css)) reveals every tab pane, so Price,
Equity, Drawdown, P&L and the period matrix all land in the export. Screen
and print share one render tree — canvas would rasterize and race the
synchronous print dialog.

## Surface census (post-#1463)

| Surface | Renders | Source |
|---|---|---|
| Price (candles + trade markers, hover cards, log scale) | `CandlestickChart` | family |
| Equity (log $ / linear %) · Drawdown | `TimeSeries` | family |
| Per-trade P&L (open-leg state) | `TradeReturnChart` | family |
| Period matrix (3 metrics × 3 granularities) | `ReturnsMatrix` | family |
| Trade log (ReactNode cells, `.ts-trade-open` row state) | `TradeLogTable` + `DirectionPill` | family (cell wiring app-local) |
| KPI strip | `KpiStrip` / `Kpi` | family |
| Library cards | `TearsheetCard` (+`TearsheetCardKpis`) | family (head composition app-local) |
| Live badge | `LiveBadge` | family (`generated_at` null-gating app-local: `live-metrics.tsx`) |
| Statistics pivot | `PivotStatsTable` | **app-local** — transposed pivot grammar not promoted (its `.ts-pivot-*` screen/print CSS ships in the family sheet) |
| Current position banner | `CurrentPosition` | **app-local** — same: dress in the family sheet, wiring here |

Chart view sync (`ViewWindow`, lookback presets), scales, legends, and the
seg toggle all come from the family barrel. Data derivation (`series.ts`,
`stats.ts`, `pivot-stats.ts`, `trades.ts`, `types.ts` full schema) is
app-owned data wiring and stays put; components take render-ready props.

Screen-only reuse: the homepage preview deck
(`components/landing/StrategySuite.tsx`) renders the same family
`CandlestickChart` (compact) — one engine backs every price surface in this
app. Do not fork the engine per surface.
