/**
 * finance-charts family barrel (#1450) — quant tearsheet surfaces promoted
 * from the design reference's finance page. Time-series charts ride
 * TradingView Lightweight Charts (the engine ruling — see
 * frontend/olympus/lib/CHARTS.md); MonthlyReturns is categorical and stays a
 * token-tinted table. Re-exported from the package root by src/index.ts.
 */

export { PriceChart, type PriceChartProps } from "./PriceChart";
export { EquityCurve, type EquityCurveProps } from "./EquityCurve";
export { DrawdownPlot, type DrawdownPlotProps } from "./DrawdownPlot";
export {
  MonthlyReturns,
  type MonthlyReturnsProps,
  type MonthlyReturnRow,
} from "./MonthlyReturns";
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
export {
  PRICE_CHART_DEMO,
  EQUITY_CURVE_DEMO,
  DRAWDOWN_DEMO,
  MONTHLY_RETURNS_DEMO,
} from "./demo-data";
