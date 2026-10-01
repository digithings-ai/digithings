/**
 * The book's window math: beta and alpha off the drawn (rebased) legs (#4429).
 *
 * Kept in a React-free module so the reads' arithmetic is unit-testable
 * without mounting the band. `QuantSection` imports both; the chart itself
 * never sees these — it draws the rebased legs, the reads measure them.
 */

export interface DrawnPoint {
  t: string;
  v: number;
}

/** Beta of the portfolio leg against the benchmark leg, from the in-window
    daily returns paired by date — or null when the window is too thin to
    measure. Computed off the rebased legs, where a step from `a` to `b`
    is a daily return of `(b − a) / (a + 100)`. */
export function windowBeta(portfolio: DrawnPoint[], benchmark: DrawnPoint[]): number | null {
  const benchByDate = new Map(benchmark.map((point) => [point.t, point.v]));
  const rp: number[] = [];
  const rm: number[] = [];
  for (let i = 1; i < portfolio.length; i++) {
    const prev = portfolio[i - 1];
    const curr = portfolio[i];
    const benchPrev = benchByDate.get(prev.t);
    const benchCurr = benchByDate.get(curr.t);
    if (benchPrev === undefined || benchCurr === undefined) continue;
    const pBase = prev.v + 100;
    const mBase = benchPrev + 100;
    if (!(pBase > 0) || !(mBase > 0)) continue;
    rp.push((curr.v - prev.v) / pBase);
    rm.push((benchCurr - benchPrev) / mBase);
  }
  if (rp.length < 2) return null;
  const meanP = rp.reduce((a, b) => a + b, 0) / rp.length;
  const meanM = rm.reduce((a, b) => a + b, 0) / rm.length;
  let cov = 0;
  let variance = 0;
  for (let i = 0; i < rp.length; i++) {
    cov += (rp[i] - meanP) * (rm[i] - meanM);
    variance += (rm[i] - meanM) * (rm[i] - meanM);
  }
  if (!(variance > 0)) return null;
  return cov / variance;
}

/** Alpha: the window's portfolio return minus beta times the benchmark's, in
    percentage points — the part of the return the market move didn't explain. */
export function windowAlpha(
  portfolioReturn: number | null,
  benchmarkReturn: number | null,
  beta: number | null,
): number | null {
  if (portfolioReturn === null || benchmarkReturn === null || beta === null) return null;
  return portfolioReturn - beta * benchmarkReturn;
}

/**
 * Annualization basis for the book's window ratios (#4429).
 *
 * Standard 252 trading days — a deliberate call. The benchmark-relative reads
 * (excess, info ratio, alpha, beta) are all computed on legs paired by shared
 * dates, so pairs only exist where both legs printed: the comparison universe
 * is already trading-day shaped, and the book's weekend P&L folds into the
 * next paired daily, exactly how 24/7 funds report against equity benchmarks.
 * Annualizing the book's Sharpe on 365 next to a 252-shaped info ratio would
 * make adjacent numbers incomparable. CAGR needs no basis: it uses the actual
 * calendar fraction.
 */
export const TRADING_DAYS_PER_YEAR = 252;

/** In-window daily simple returns of a drawn (rebased) leg. A step from `a`
    to `b` on a leg rebased to 0 at the window start is `(b − a) / (a + 100)`. */
function drawnDailies(leg: DrawnPoint[]): number[] {
  const out: number[] = [];
  for (let i = 1; i < leg.length; i++) {
    const base = leg[i - 1].v + 100;
    if (!(base > 0)) continue;
    out.push((leg[i].v - leg[i - 1].v) / base);
  }
  return out;
}

function mean(values: number[]): number {
  return values.reduce((a, b) => a + b, 0) / values.length;
}

/** Population standard deviation — the window IS the population measured. */
function stdev(values: number[]): number {
  const m = mean(values);
  return Math.sqrt(mean(values.map((v) => (v - m) * (v - m))));
}

/** Mean and risk of the leg's in-window dailies, or null when too thin. */
export function windowRiskStats(leg: DrawnPoint[]): { mean: number; sd: number } | null {
  const dailies = drawnDailies(leg);
  if (dailies.length < 2) return null;
  return { mean: mean(dailies), sd: stdev(dailies) };
}

/** Annualized Sharpe at rf=0, or null when the window cannot be measured. */
export function windowSharpe(leg: DrawnPoint[]): number | null {
  const stats = windowRiskStats(leg);
  if (!stats || !(stats.sd > 0)) return null;
  return (stats.mean / stats.sd) * Math.sqrt(TRADING_DAYS_PER_YEAR);
}

/** Annualized Sortino (downside deviation over sub-zero dailies), or null. */
export function windowSortino(leg: DrawnPoint[]): number | null {
  const dailies = drawnDailies(leg);
  if (dailies.length < 2) return null;
  const downside = Math.sqrt(mean(dailies.map((d) => (d < 0 ? d * d : 0))));
  if (!(downside > 0)) return null;
  return (mean(dailies) / downside) * Math.sqrt(TRADING_DAYS_PER_YEAR);
}

/** Annualized information ratio of the paired daily EXCESS returns, or null
    when the legs overlap on fewer than 2 dailies or the excess never varies. */
export function windowInfoRatio(
  portfolio: DrawnPoint[],
  benchmark: DrawnPoint[],
): number | null {
  const benchByDate = new Map(benchmark.map((point) => [point.t, point.v]));
  const excess: number[] = [];
  for (let i = 1; i < portfolio.length; i++) {
    const prev = portfolio[i - 1];
    const curr = portfolio[i];
    const benchPrev = benchByDate.get(prev.t);
    const benchCurr = benchByDate.get(curr.t);
    if (benchPrev === undefined || benchCurr === undefined) continue;
    const pBase = prev.v + 100;
    const mBase = benchPrev + 100;
    if (!(pBase > 0) || !(mBase > 0)) continue;
    excess.push((curr.v - prev.v) / pBase - (benchCurr - benchPrev) / mBase);
  }
  if (excess.length < 2) return null;
  const sd = stdev(excess);
  if (!(sd > 0)) return null;
  return (mean(excess) / sd) * Math.sqrt(TRADING_DAYS_PER_YEAR);
}

/** A unitless ratio, or an em dash when the window cannot be measured. */
export function fmtRatio(value: number | null): string {
  if (value === null) return "—";
  const sign = value > 0 ? "+" : value < 0 ? "−" : "";
  return `${sign}${Math.abs(value).toFixed(2)}`;
}
