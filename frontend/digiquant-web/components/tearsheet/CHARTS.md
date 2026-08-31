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

## Schema 1.3 — DCA kind (#3172)

`TearsheetData.dca` is an optional `TearsheetDcaBreakdown`. Slapper payloads
omit it and render unchanged. Drive off **null KPIs** (`win_rate_pct` /
`profit_factor` / `long` / `short`), not a slug allowlist.

| Surface | Renders | Source |
|---|---|---|
| Valuation rails (log spot + low/median/high) | `MultiTimeSeries` | family (#3172) |
| Risk-band strip (0–100, labelled bands) | `RiskBandStrip` | family (#3172) |
| Allocation (MTM allocated % vs cash; fill markers) | `AllocationStepChart` + cost-basis overlay | family |
| Equity overlay (SDCA vs buy & hold) | `MultiTimeSeries` on the Equity tab | family |

Rails / risk / cost-basis / lump / flat series are optional diagnostic
fields (`rails`, `risk_curve`, `cost_basis_curve`, `lump_equity_curve`,
`flat_dca_equity_curve`). Tabs degrade away when a series is absent —
the publish path copies #3168 diagnostic columns so these charts do not
degrade on a shipped `btc_sdca` payload.

Library cards for `kind === "dca"` (or when `vs_lump_pct` is present)
headline **vs buy & hold**, **total return**, **max drawdown**, and
**allocated %**. vs-flat DCA is not a public comparable.
Do not present curve-sign `buy_days`/`sell_days` as fill counts.

Latest signal for a DCA book is **buy / sell / hold** plus the remaining-book
rate (percent of remaining cash or remaining BTC), as of `period_end` (3-day
delay). Allocated is MTM, never a negative "Deployed". The primary chart is
**Fills** (`AllocationStepChart` with sized buy/sell markers). The risk tab is
the **composite valuation index** (power law + M2 + DXY).

Public title is **BTC SDCA Strat**. Honesty (`beats_flat_dca_oos` false,
backtest only) lives in notes, not title chips.

Band labels: `<10 Fire sale · 10–25 Accumulate · 25–50 Value · 50–75 Above mid · 75–95 Hot · 95–100 Bubble`.
All `dca.*_pct` fields are ×100 percents.
