/**
 * Pure, derived performance statistics shared by the strategy-suite cards and
 * the full tearsheet. Total net profit % on a multi-year compounded backtest is
 * uninformative ("+27M%"); these helpers normalize it to annualized, risk-adjusted
 * and frequency terms that compare across strategies and horizons.
 *
 * All functions are pure and side-effect free. Percentages are expressed as
 * whole-number percents (e.g. 12.5 == 12.5%), matching the rest of the schema.
 */

const MS_PER_YEAR = 365.25 * 24 * 3600 * 1000;

/** Fractional years between two ISO dates ("YYYY-MM-DD"). Floored at 1e-9 to keep
 *  it strictly positive so it is always safe as a divisor / root exponent. */
export function yearsBetween(startISO: string, endISO: string): number {
  const ms = new Date(endISO).getTime() - new Date(startISO).getTime();
  return Math.max(ms / MS_PER_YEAR, 1e-9);
}

/** Annualized return (CAGR %) implied by a total net-profit %, for the index cards
 *  (no capital fields). growth = 1 + netProfitPct/100; 0 if growth is non-positive. */
export function cagrPctFromGrowth(netProfitPct: number, startISO: string, endISO: string): number {
  const growth = 1 + netProfitPct / 100;
  if (growth <= 0) return 0;
  const years = yearsBetween(startISO, endISO);
  return (Math.pow(growth, 1 / years) - 1) * 100;
}

/** Annualized return (CAGR %) from initial and final capital, for the detail page. */
export function cagrPct(initial: number, final: number, startISO: string, endISO: string): number {
  if (initial <= 0 || final <= 0) return 0;
  const years = yearsBetween(startISO, endISO);
  return (Math.pow(final / initial, 1 / years) - 1) * 100;
}

/** Average number of closed trades per year — a frequency / turnover signal. */
export function tradesPerYear(totalTrades: number, startISO: string, endISO: string): number {
  return totalTrades / yearsBetween(startISO, endISO);
}

/** Mean per-trade return (%); 0 for an empty set. More representative than a
 *  dollar average, which is dominated by late compounding trades. */
export function avgTradePct(pnlPcts: number[]): number {
  if (pnlPcts.length === 0) return 0;
  return pnlPcts.reduce((sum, p) => sum + p, 0) / pnlPcts.length;
}

/** Calmar ratio: annualized return over the (positive) magnitude of max drawdown.
 *  `maxDrawdownPct` is negative in the schema; 0 if drawdown is ~flat. */
export function calmar(cagrPctValue: number, maxDrawdownPct: number): number {
  return Math.abs(maxDrawdownPct) < 1e-9 ? 0 : cagrPctValue / Math.abs(maxDrawdownPct);
}
