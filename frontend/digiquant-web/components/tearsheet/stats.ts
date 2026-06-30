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

function downsideStd(xs: number[], threshold = 0): number {
  const below = xs.filter((x) => x < threshold).map((x) => x - threshold);
  if (below.length < 2) return 0;
  const m = mean(below);
  const v = below.reduce((a, x) => a + (x - m) ** 2, 0) / (below.length - 1);
  return Math.sqrt(v);
}

const TRADING_DAYS = 252;

/** Annualized Sharpe from daily returns (risk-free ≈ 0). */
export function sharpeFromReturns(returns: number[]): number | null {
  if (returns.length < 2) return null;
  const std = sampleStd(returns);
  if (std < 1e-12) return null;
  return (mean(returns) / std) * Math.sqrt(TRADING_DAYS);
}

/** Annualized Sortino from daily returns (downside vs 0). */
export function sortinoFromReturns(returns: number[]): number | null {
  if (returns.length < 2) return null;
  const dstd = downsideStd(returns, 0);
  if (dstd < 1e-12) return null;
  return (mean(returns) / dstd) * Math.sqrt(TRADING_DAYS);
}

/** Annualized volatility (%) from daily returns. */
export function annualizedVolPct(returns: number[]): number | null {
  if (returns.length < 2) return null;
  return sampleStd(returns) * Math.sqrt(TRADING_DAYS) * 100;
}

/** Omega ratio at threshold 0 — sum of gains / sum of losses. */
export function omegaFromReturns(returns: number[], threshold = 0): number | null {
  if (returns.length === 0) return null;
  let gains = 0;
  let losses = 0;
  for (const r of returns) {
    if (r > threshold) gains += r - threshold;
    else losses += threshold - r;
  }
  if (losses < 1e-12) return gains > 0 ? null : 0;
  return gains / losses;
}

/** Net profit % divided by |max drawdown %| — capital recovery efficiency. */
export function recoveryFactor(netProfitPct: number, maxDrawdownPct: number): number | null {
  if (Math.abs(maxDrawdownPct) < 1e-9) return null;
  return netProfitPct / Math.abs(maxDrawdownPct);
}

/** CAGR excess vs buy-and-hold of the underlying (same window). */
export function alphaVsBuyHold(
  ohlc: { t: string; c: number }[] | undefined,
  stratInitial: number,
  stratFinal: number,
  startISO: string,
  endISO: string,
): number | null {
  if (!ohlc || ohlc.length < 2) return null;
  const lo = new Date(startISO).getTime();
  const hi = new Date(endISO).getTime();
  const window = ohlc.filter((b) => {
    const t = new Date(b.t).getTime();
    return t >= lo && t <= hi;
  });
  if (window.length < 2) return null;
  const stratCagr = cagrPct(stratInitial, stratFinal, startISO, endISO);
  const bhCagr = cagrPct(window[0].c, window[window.length - 1].c, window[0].t, window[window.length - 1].t);
  return stratCagr - bhCagr;
}

export interface DerivedRiskMetrics {
  sharpe: number | null;
  sortino: number | null;
  calmar: number | null;
  omega: number | null;
  volatilityPct: number | null;
  alphaPct: number | null;
  recovery: number | null;
}

/** Risk stats derived from the equity curve (+ optional OHLC for alpha). */
export function deriveRiskMetrics(
  equity: { t: string; v: number }[],
  ohlc: { t: string; c: number }[] | undefined,
  initial: number,
  final: number,
  startISO: string,
  endISO: string,
  maxDrawdownPct: number,
  netProfitPct: number,
  overrides?: { sharpe?: number | null; sortino?: number | null; calmar?: number | null },
): DerivedRiskMetrics {
  const rets = dailyReturnsFromEquity(equity);
  const cagr = cagrPct(initial, final, startISO, endISO);
  const calmarVal = Math.abs(maxDrawdownPct) < 1e-9 ? null : calmar(cagr, maxDrawdownPct);
  return {
    sharpe: overrides?.sharpe ?? sharpeFromReturns(rets),
    sortino: overrides?.sortino ?? sortinoFromReturns(rets),
    calmar: overrides?.calmar ?? calmarVal,
    omega: omegaFromReturns(rets),
    volatilityPct: annualizedVolPct(rets),
    alphaPct: alphaVsBuyHold(ohlc, initial, final, startISO, endISO),
    recovery: recoveryFactor(netProfitPct, maxDrawdownPct),
  };
}

/** Format a ratio tile; null/NaN → em dash. */
export function fmtRatio(v: number | null | undefined, digits = 2): string {
  if (v === null || v === undefined || Number.isNaN(v)) return "—";
  return v.toLocaleString("en-US", { minimumFractionDigits: digits, maximumFractionDigits: digits });
}

export interface AnnualPerformanceRow {
  year: number;
  returnPct: number | null;
  maxDrawdownPct: number | null;
  trades: number;
  winRatePct: number | null;
  sharpe: number | null;
}

/** Calendar-year slices for the advanced statistics table. */
export function annualPerformanceRows(
  equity: { t: string; v: number }[],
  drawdown: { t: string; v: number }[],
  trades: { exit_date: string; pnl: number; pnl_pct: number }[],
): AnnualPerformanceRow[] {
  if (equity.length === 0) return [];

  const years = new Set<number>();
  for (const p of equity) years.add(new Date(p.t).getUTCFullYear());
  for (const t of trades) {
    if (t.exit_date) years.add(new Date(t.exit_date).getUTCFullYear());
  }

  const sorted = [...years].sort((a, b) => a - b);
  return sorted.map((year) => {
    const eqYear = equity.filter((p) => new Date(p.t).getUTCFullYear() === year);
    const ddYear = drawdown.filter((p) => new Date(p.t).getUTCFullYear() === year);
    const closed = trades.filter((t) => t.exit_date && new Date(t.exit_date).getUTCFullYear() === year);

    let returnPct: number | null = null;
    if (eqYear.length >= 2) {
      const first = eqYear[0].v;
      const last = eqYear[eqYear.length - 1].v;
      returnPct = first > 0 ? (last / first - 1) * 100 : null;
    }

    let maxDrawdownPct: number | null = null;
    if (ddYear.length > 0) {
      maxDrawdownPct = ddYear.reduce((min, p) => (p.v < min ? p.v : min), ddYear[0].v);
    }

    const wins = closed.filter((t) => t.pnl > 0).length;
    const winRatePct = closed.length > 0 ? (wins / closed.length) * 100 : null;

    const rets = dailyReturnsFromEquity(eqYear);
    const sharpe = sharpeFromReturns(rets);

    return {
      year,
      returnPct,
      maxDrawdownPct,
      trades: closed.length,
      winRatePct,
      sharpe,
    };
  });
}
