import type { NavChartPoint, PositionHistoryRow } from './types';

export type PositionContributionPoint = {
  date: string;
  /** Cumulative attributed portfolio return from this holding (percentage points). */
  cumPp: number;
  /** Increment on this NAV step (percentage points). */
  dailyPp: number;
};

function priceOnOrBefore(
  sorted: Array<{ date: string; close: number }>,
  iso: string
): number | null {
  let lo = 0;
  let hi = sorted.length - 1;
  let ans = -1;
  while (lo <= hi) {
    const mid = (lo + hi) >> 1;
    if (sorted[mid].date <= iso) {
      ans = mid;
      lo = mid + 1;
    } else hi = mid - 1;
  }
  return ans >= 0 ? sorted[ans].close : null;
}

/**
 * Weight % of ticker at each NAV date (last known row with date ≤ that NAV date).
 */
function weightsAlongNavDates(
  navDates: string[],
  history: PositionHistoryRow[],
  ticker: string
): number[] {
  const t = ticker.toUpperCase();
  const rows = history
    .filter((r) => r.ticker.toUpperCase() === t)
    .sort((a, b) => a.date.localeCompare(b.date));
  const out: number[] = [];
  let j = 0;
  let lastW = 0;
  for (const d of navDates) {
    while (j < rows.length && rows[j].date <= d) {
      lastW = rows[j].weight_pct;
      j++;
    }
    out.push(lastW);
  }
  return out;
}

/**
 * Cumulative portfolio return contribution (percentage points) from this name's price moves,
 * weighted by position size between consecutive NAV snapshot dates:
 * Σ (weight_{t-1}/100) × (P_t/P_{t-1} − 1) × 100.
 */
export function buildPositionContributionToNavSeries(
  navSnaps: NavChartPoint[],
  positionHistory: PositionHistoryRow[],
  ticker: string,
  priceSorted: Array<{ date: string; close: number }>
): PositionContributionPoint[] {
  const prices = [...priceSorted].sort((a, b) => a.date.localeCompare(b.date));
  if (prices.length < 2 || navSnaps.length < 2) return [];

  const uniqNav = navSnaps
    .slice()
    .sort((a, b) => a.date.localeCompare(b.date))
    .filter((s, i, arr) => i === 0 || s.date !== arr[i - 1].date);

  const navDates = uniqNav.map((s) => s.date);
  if (navDates.length < 2) return [];

  const weights = weightsAlongNavDates(navDates, positionHistory, ticker);

  const out: PositionContributionPoint[] = [{ date: navDates[0], cumPp: 0, dailyPp: 0 }];
  let cum = 0;

  for (let i = 1; i < navDates.length; i++) {
    const d0 = navDates[i - 1];
    const d1 = navDates[i];
    const w = weights[i - 1];
    const p0 = priceOnOrBefore(prices, d0);
    const p1 = priceOnOrBefore(prices, d1);
    let dailyPp = 0;
    if (p0 != null && p1 != null && p0 > 0) {
      const r = p1 / p0 - 1;
      dailyPp = (w / 100) * r * 100;
    }
    cum += dailyPp;
    out.push({ date: d1, cumPp: cum, dailyPp });
  }
  return out;
}
