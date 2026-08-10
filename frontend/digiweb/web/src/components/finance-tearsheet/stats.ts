/**
 * The two derived statistics the ReturnsMatrix volatility metric needs
 * (#1463), verbatim from frontend/digiquant-web/components/tearsheet/stats.ts.
 * The full derived-stats library (CAGR, Sharpe/Sortino/Omega, annual rows …)
 * is app-owned data wiring and stays with the consumers.
 */

/** Daily simple returns from a mark-to-market equity curve. */
export function dailyReturnsFromEquity(points: { v: number }[]): number[] {
  const rets: number[] = [];
  for (let i = 1; i < points.length; i++) {
    const prev = points[i - 1].v;
    if (prev > 0) rets.push(points[i].v / prev - 1);
  }
  return rets;
}

function mean(xs: number[]): number {
  return xs.length ? xs.reduce((a, b) => a + b, 0) / xs.length : 0;
}

function sampleStd(xs: number[]): number {
  if (xs.length < 2) return 0;
  const m = mean(xs);
  const v = xs.reduce((a, x) => a + (x - m) ** 2, 0) / (xs.length - 1);
  return Math.sqrt(v);
}

const TRADING_DAYS = 252;

/** Annualized volatility (%) from daily returns. */
export function annualizedVolPct(returns: number[]): number | null {
  if (returns.length < 2) return null;
  return sampleStd(returns) * Math.sqrt(TRADING_DAYS) * 100;
}
