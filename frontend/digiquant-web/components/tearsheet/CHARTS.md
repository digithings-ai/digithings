# digiquant tearsheet — chart & table engine ruling (F2 adoption pass, #1450)

> **Ruling: the tearsheet stays on its local print-first SVG renderer
> (`charts.tsx`). The promoted `@digithings/web` finance family
> (finance-charts / finance-composites — TradingView Lightweight Charts,
> canvas) is NOT adopted on any tearsheet surface.** Same ruling as olympus'
> `OlympusTearsheetView` ([frontend/olympus/lib/CHARTS.md](../../../olympus/lib/CHARTS.md)):
> print-first SVG must not be forced onto canvas.

## Why — two hard constraints

1. **Every chart surface participates in the PDF export.** "Download PDF"
   (`print-tearsheet.ts`) `flushSync`-re-renders the *same* chart component
   instances at full span (`PRINT_FULL_VIEW`, linear scale) and then calls
   `window.print()`; the print block in [`app/globals.css`](../../app/globals.css)
   reveals every tab pane (`.ts-tab-pane[hidden] { display: block !important }`),
   so Price, Equity, Drawdown, P&L and the period matrix all land in the
   export. There is **no screen-only chart pane to split off** — screen and
   print share one render tree. Lightweight Charts paints canvas on rAF:
   it would rasterize in the PDF and race the synchronous print dialog,
   where SVG re-renders synchronously and prints crisply.
2. **The interaction contract is not expressible in the promoted primitives.**
   The four series surfaces share one normalized `ViewWindow` (wheel-zoom /
   drag-pan / double-click synced across charts, lookback presets matched
   back via `matchLookbackPreset`), the candles carry trade entry/exit
   markers with hover cards, scales include log and symlog, and P&L bars
   distinguish realized vs open legs. `EquityCurve` / `DrawdownPlot` /
   `PriceChart` (`useFinanceChart`) are display surfaces: no external view
   control, no marker/tooltip API, no scale prop, teardown-rebuild on every
   data change.

Theming is already canon-compliant without an engine swap: the SVG paints
through chart classes in `@digithings/design/tearsheet/styles.css`, which
consume `[data-theme]` tokens — theme flips re-skin via CSS with no JS
re-theme step.

## Surface census (adoption verdict per surface)

| Surface | Local renderer | Promoted candidate | Verdict |
|---|---|---|---|
| Price (candles + trade markers) | `CandlestickChart` | `PriceChart` | Keep local: prints; markers/hover/log/view-sync missing from primitive. |
| Equity (log $ / linear %) | `TimeSeries` | `EquityCurve` | Keep local: prints; log toggle + view-sync. |
| Drawdown | `TimeSeries` (`zeroBaseline`, down tone) | `DrawdownPlot` | Keep local: prints; view-sync. |
| Per-trade P&L | `TradeReturnChart` | — (no promoted bar primitive) | Keep local. |
| Period matrix | `ReturnsMatrix` | `MonthlyReturns` | Keep local: matrix is a superset — 3 metrics × 3 periods, data-driven max-abs tint, signed compact % (crypto-scale returns), compounded Year column, `.ts-matrix-cell` print rules. `MonthlyReturns` covers only the monthly-return slice (fixed `peak` tint, unsigned 1-dp cells, arithmetic-sum default total, up-tint would misread volatility). |
| Statistics pivot | `PivotStatsTable` | `SortableTable` / `PrecisionTable` | Keep local: transposed grammar (metrics as rows, slices as columns); print stacks both pivots. |
| Trade log | `TradeLogTable` | `SortableTable` | Keep local: ReactNode cells (`TradeReturnCell` unrealized mark, `ts-dir` pills), per-row open-state class, sticky-head scroll + print rules; `SortableTable` formats cells to strings and adds sort affordances (shipped-look change). |
| KPI strip | `Kpi` (`.ts-kpis-primary`) | `PerfMetrics` | Keep local: 6-up responsive card strip vs 4-column-max hairline block; toned ReactNode values; `.ts-kpi` print rules. |
| Library cards | `StrategyCard` (`.ts-card` anchor) | `Card` + `Badge` | Keep local: anchor semantics + hover-lift gradient dress exist in neither `ctl-card` dress; `.ts-card` print rules. |
| Live badge | `LiveMetricsBadge` | `Badge` | Keep local: pulsing-dot animation grammar. |

Screen-only reuse: the homepage preview deck
(`components/landing/StrategySuite.tsx`) renders the same `CandlestickChart`
(compact, non-interactive) — one engine backs every price surface in this
app, and the preview shows the same trade markers the promoted `PriceChart`
cannot draw. Do not fork the engine per surface.

## Recorded gaps (what would reopen this ruling)

The promoted family would need, before any tearsheet surface migrates:

- a print-grade (vector) export path — canvas is disqualifying while
  "Download PDF" is a shipped feature;
- external view-window control + cross-chart sync + preset matching;
- a trade-marker + hover-card API on `PriceChart`;
- log/symlog scale props;
- `MonthlyReturns`: metric semantics (drawdown/volatility), signed compact
  formatting, data-driven tint scaling, compounded totals;
- `SortableTable`: ReactNode cells, per-row state hook, print grammar;
- `Card`: anchor/render composition plus a tearsheet dress.

Data wiring (`series.ts`, `stats.ts`, `pivot-stats.ts`, `trades.ts`,
`format.ts`, `types.ts`) is app-owned either way and stays put.
