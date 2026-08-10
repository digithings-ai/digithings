/**
 * finance-tearsheet family barrel (#1463) — the print-grade SVG tearsheet
 * grammar reverse-promoted from frontend/digiquant-web/components/tearsheet/.
 * Everything here participates in the PDF export (flushSync + window.print
 * over ONE render tree), so the charts are pure SVG — the canvas
 * finance-charts / finance-composites families are the screen-only DASHBOARD
 * grammar. The split ruling lives in frontend/digiweb/CHARTS.md.
 *
 * Wiring (consuming app):
 *   globals.css   @import "@digithings/web/styles/finance-tearsheet.css";
 *                 (plainly — the sheet manages its own layering)
 *                 @source "<path-to>/digiweb/web/src/components/finance-tearsheet";
 * Data derivation (series clipping, pivot stats, trade sorting, CAGR et al.)
 * stays app-owned — components take render-ready props.
 */

export {
  CandlestickChart,
  TimeSeries,
  SignedBars,
  ContributionReturnChart,
  TradeReturnChart,
  SegToggle,
  ChartLegend,
  ChartResetButton,
  LOOKBACK_OPTIONS,
  viewWindowForPreset,
  viewWindowLastYear,
  matchLookbackPreset,
  viewsNear,
  type CandlestickChartProps,
  type TimeSeriesProps,
  type SignedBarsProps,
  type ContributionReturnChartProps,
  type ContributionReturnPoint,
  type TradeReturnChartProps,
  type ChartScale,
  type ChartTone,
  type ViewWindow,
  type LookbackPreset,
} from "./charts";
export { ReturnsMatrix, type ReturnsPeriod, type MatrixMetric } from "./ReturnsMatrix";
export { KpiStrip, Kpi, type KpiStripProps, type KpiProps } from "./KpiStrip";
export {
  TradeLogTable,
  DirectionPill,
  type TradeLogTableProps,
  type TradeLogColumn,
  type TradeLogRow,
} from "./TradeLogTable";
export {
  TearsheetCard,
  TearsheetCardKpis,
  TearsheetCardKpi,
  type TearsheetCardProps,
} from "./TearsheetCard";
export { LiveBadge, type LiveBadgeProps } from "./LiveBadge";
export { PRINT_FULL_VIEW, runTearsheetPrint } from "./print";
export {
  isOpenTrade,
  type TearsheetSeriesPoint,
  type TearsheetOhlcBar,
  type TearsheetTrade,
  type TradeReturnBar,
} from "./types";
export { fmtCompact, fmtPct, fmtMoney, fmtNum, toneClass } from "./format";
export { dailyReturnsFromEquity, annualizedVolPct } from "./stats";
export { TEARSHEET_DEMO } from "./demo-data";
