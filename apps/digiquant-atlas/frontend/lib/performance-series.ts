import type { NavChartPoint } from './types';

export type DateRangeKey = 'itd' | '1m' | '3m' | 'ytd';

export function filterByDateRange<T extends { date: string }>(rows: T[], key: DateRangeKey): T[] {
  if (!rows.length || key === 'itd') return rows;
  const last = rows[rows.length - 1].date;
  const lastD = new Date(`${last}T12:00:00Z`);
  if (Number.isNaN(lastD.getTime())) return rows;

  if (key === 'ytd') {
    const y = lastD.getUTCFullYear();
    const start = `${y}-01-01`;
    return rows.filter((r) => r.date >= start);
  }

  const cut = new Date(lastD);
  if (key === '1m') cut.setUTCMonth(cut.getUTCMonth() - 1);
  else cut.setUTCMonth(cut.getUTCMonth() - 3);
  const cutStr = cut.toISOString().slice(0, 10);
  return rows.filter((r) => r.date >= cutStr);
}

export function parseDateRangeKey(v: string | null): DateRangeKey {
  if (v === '1m' || v === '3m' || v === 'ytd' || v === 'itd') return v;
  return 'itd';
}

export type PerformanceChartView =
  | 'nav'
  | 'drawdown'
  | 'daily_returns'
  | 'rolling';

export function parseChartViewKey(v: string | null): PerformanceChartView {
  if (v === 'allocation' || v === 'cash') return 'nav';
  const allowed: PerformanceChartView[] = ['nav', 'drawdown', 'daily_returns', 'rolling'];
  if (v && allowed.includes(v as PerformanceChartView)) return v as PerformanceChartView;
  return 'nav';
}

/** Per-day return % and NAV re-based to 100 at range start (for combo chart). */
export function buildDailyReturnsWithNavIndex(
  snaps: NavChartPoint[]
): Array<{ date: string; dailyPct: number | null; navIndex: number }> {
  if (!snaps.length) return [];
  const base = snaps[0].nav;
  return snaps.map((s, i) => {
    const navIndex = base > 0 ? (s.nav / base) * 100 : 100;
    if (i === 0) return { date: s.date, dailyPct: null, navIndex };
    const prev = snaps[i - 1].nav;
    const dailyPct =
      prev > 0 ? ((s.nav - prev) / prev) * 100 : null;
    return { date: s.date, dailyPct, navIndex };
  });
}

/** Underwater series (% from running peak). */
export function buildDrawdownSeries(snaps: NavChartPoint[]): Array<{ date: string; drawdown: number }> {
  if (!snaps.length) return [];
  let peak = snaps[0].nav;
  return snaps.map((s) => {
    if (s.nav > peak) peak = s.nav;
    const dd = peak > 0 ? ((s.nav - peak) / peak) * 100 : 0;
    return { date: s.date, drawdown: dd };
  });
}

/**
 * When history is shorter than `baseWindow + 2` trading days, shrink the rolling
 * window so we still produce a sparse rolling series instead of all nulls.
 */
export function computeEffectiveRollingWindow(snapsLength: number, baseWindow = 21): number {
  if (snapsLength < 2) return baseWindow;
  if (snapsLength >= baseWindow + 2) return baseWindow;
  return Math.max(3, Math.min(baseWindow, Math.max(2, snapsLength - 2)));
}

/** Rolling annualized vol and Sharpe (Rf = 0) over `window` trading days. */
export function buildRollingSharpeVol(
  snaps: NavChartPoint[],
  window = 21
): Array<{ date: string; sharpe: number | null; volAnn: number | null }> {
  if (snaps.length < 2) return snaps.map((s) => ({ date: s.date, sharpe: null, volAnn: null }));
  const effWindow = computeEffectiveRollingWindow(snaps.length, window);
  const navs = snaps.map((s) => s.nav);
  const dates = snaps.map((s) => s.date);
  const out: Array<{ date: string; sharpe: number | null; volAnn: number | null }> = [];
  for (let i = 0; i < snaps.length; i++) {
    if (i < effWindow) {
      out.push({ date: dates[i], sharpe: null, volAnn: null });
      continue;
    }
    const rets: number[] = [];
    for (let j = i - effWindow + 1; j <= i; j++) {
      const prev = navs[j - 1];
      const cur = navs[j];
      if (prev > 0) rets.push((cur - prev) / prev);
    }
    if (rets.length < 2) {
      out.push({ date: dates[i], sharpe: null, volAnn: null });
      continue;
    }
    const mean = rets.reduce((a, b) => a + b, 0) / rets.length;
    const variance = rets.reduce((s, r) => s + (r - mean) ** 2, 0) / rets.length;
    const sd = Math.sqrt(variance);
    const volAnn = sd * Math.sqrt(252) * 100;
    const annRet = mean * 252 * 100;
    const sharpe = volAnn > 0 ? annRet / volAnn : null;
    out.push({ date: dates[i], sharpe, volAnn });
  }
  return out;
}
