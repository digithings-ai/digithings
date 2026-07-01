import type { NavChartPoint, ServerPortfolioMetrics } from './types';

/** Daily simple returns from consecutive NAV levels. */
export function dailySimpleReturnsFromNavs(navs: number[]): number[] {
  const out: number[] = [];
  for (let i = 1; i < navs.length; i++) {
    if (navs[i - 1] > 0) out.push((navs[i] - navs[i - 1]) / navs[i - 1]);
  }
  return out;
}

/**
 * Sharpe ratio (Rf = 0), aligned with `scripts/update_tearsheet.py`:
 * `returns.mean() * 252 / (returns.std() * np.sqrt(252))` on daily simple returns.
 */
export function sharpeRatioFromDailyReturns(returns: number[]): number {
  if (returns.length < 2) return 0;
  const mean = returns.reduce((a, b) => a + b, 0) / returns.length;
  const variance = returns.reduce((s, r) => s + (r - mean) ** 2, 0) / returns.length;
  const std = Math.sqrt(variance);
  if (std === 0) return 0;
  return (mean / std) * Math.sqrt(252);
}

/** Sample std of daily returns, annualized, as a percentage. */
export function annualizedVolatilityPctFromDailyReturns(returns: number[]): number {
  if (returns.length < 2) return 0;
  const mean = returns.reduce((a, b) => a + b, 0) / returns.length;
  const variance = returns.reduce((s, r) => s + (r - mean) ** 2, 0) / returns.length;
  return Math.sqrt(variance) * Math.sqrt(252) * 100;
}

/** Maximum peak-to-trough drawdown from NAV levels, returned as a negative percentage. */
export function maxDrawdownPctFromNavs(navs: number[]): number {
  if (navs.length < 2 || navs[0] <= 0) return 0;
  let peak = navs[0];
  let maxDd = 0;
  for (const nav of navs) {
    if (nav > peak) peak = nav;
    if (peak > 0) {
      const dd = (nav - peak) / peak;
      if (dd < maxDd) maxDd = dd;
    }
  }
  return maxDd * 100;
}

/**
 * Sortino (MAR = 0): annualized mean return / annualized downside deviation.
 * Downside deviation uses sqrt(mean(min(0, r)²)) over all days.
 */
export function sortinoRatioFromDailyReturns(returns: number[]): number {
  if (returns.length < 2) return 0;
  const mean = returns.reduce((a, b) => a + b, 0) / returns.length;
  const downMs = returns.reduce((s, r) => s + Math.min(0, r) ** 2, 0) / returns.length;
  const dd = Math.sqrt(downMs);
  if (dd === 0) return sharpeRatioFromDailyReturns(returns);
  return (mean / dd) * Math.sqrt(252);
}

export function computeRiskRatiosFromNavSnaps(snaps: NavChartPoint[]): {
  sharpe: number;
  sortino: number;
  annVolPct: number;
  maxDrawdownPct: number;
} | null {
  if (!snaps?.length || snaps.length < 2) return null;
  const navs = snaps.map((s) => s.nav);
  const returns = dailySimpleReturnsFromNavs(navs);
  if (returns.length < 2) return null;
  return {
    sharpe: sharpeRatioFromDailyReturns(returns),
    sortino: sortinoRatioFromDailyReturns(returns),
    annVolPct: annualizedVolatilityPctFromDailyReturns(returns),
    maxDrawdownPct: maxDrawdownPctFromNavs(navs),
  };
}

export interface EffectivePortfolioRiskMetrics {
  sharpe: number | null;
  annVolPct: number | null;
  maxDrawdownPct: number | null;
}

/** Prefer persisted portfolio_metrics values, falling back to NAV-derived values when absent. */
export function computeEffectivePortfolioRiskMetrics(
  serverMetrics: Pick<ServerPortfolioMetrics, 'sharpe' | 'volatility' | 'max_drawdown'> | null | undefined,
  snaps: NavChartPoint[]
): EffectivePortfolioRiskMetrics {
  const navMetrics = computeRiskRatiosFromNavSnaps(snaps);
  return {
    sharpe: serverMetrics?.sharpe ?? navMetrics?.sharpe ?? null,
    annVolPct: serverMetrics?.volatility ?? navMetrics?.annVolPct ?? null,
    maxDrawdownPct: serverMetrics?.max_drawdown ?? navMetrics?.maxDrawdownPct ?? null,
  };
}
