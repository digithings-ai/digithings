/**
 * Equity curve — the tearsheet's headline: cumulative equity as an area
 * series on TradingView Lightweight Charts, wearing the module accent
 * (identity, not a P&L read), token-themed with a live retheme on theme and
 * livery flips. Consumes the shared <EquityCurve/> primitive from
 * @digithings/web with its deterministic demo walk. Static display template.
 */
import { EquityCurve, EQUITY_CURVE_DEMO } from "@digithings/web";

export function EquityCurveReference() {
  return <EquityCurve data={EQUITY_CURVE_DEMO} />;
}
