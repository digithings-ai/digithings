/**
 * finance-charts family barrel (#1450) — canvas dashboard chart surfaces
 * promoted from the design reference's finance page. Time-series charts ride
 * TradingView Lightweight Charts (the engine ruling — see
 * frontend/digiweb/CHARTS.md for the canvas-vs-SVG split; print-grade
 * surfaces compose the finance-tearsheet family instead). MonthlyReturns was
 * deprecated into finance-tearsheet's ReturnsMatrix (#1463) — one matrix
 * grammar, no app consumers existed. Re-exported from the package root by
 * src/index.ts.
 */

export { PriceChart, type PriceChartProps } from "./PriceChart";
export { EquityCurve, type EquityCurveProps } from "./EquityCurve";
export { DrawdownPlot, type DrawdownPlotProps } from "./DrawdownPlot";
export {
  useFinanceChart,
  useFinanceChartPalette,
  getFinancePalette,
  readFinancePalette,
  financeChartOptions,
  tokenAlpha,
  toChartTime,
  type FinanceChartPalette,
  type FinanceSeriesPoint,
  type OhlcPoint,
  type CrosshairLabelToken,
} from "./chart-host";
export {
  useLightweightChart,
  chartChromeOptions,
  hostMonoFont,
  toLineData,
  timeToISO,
  useChartTip,
  ChartTipShell,
  type ChartChrome,
  type ChartTip,
  type UseLightweightChartConfig,
  type UseLightweightChartResult,
} from "./lw-chart";
export { PRICE_CHART_DEMO, EQUITY_CURVE_DEMO, DRAWDOWN_DEMO } from "./demo-data";
