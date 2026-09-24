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
