import { resolveFirstEntryDate } from '@/lib/position-first-entry';
import type { DashboardPositionEvent, Position, PositionHistoryRow } from '@/lib/types';

export type DrilldownWindow = '1m' | '3m' | 'ytd' | '1y' | 'itd';

export const DRILLDOWN_WINDOW_LABELS: Record<DrilldownWindow, string> = {
  '1m': '1M',
  '3m': '3M',
  ytd: 'YTD',
  '1y': '1Y',
  itd: 'ITD',
};

/** Calendar context before first open (matches prior chart padding). */
export const DRILLDOWN_ENTRY_PADDING_DAYS = 45;

export function subtractIsoDays(iso: string, days: number): string {
  const parts = iso.split('-').map(Number);
  if (parts.length < 3) return iso;
  const [y, m, d] = parts;
  const t = Date.UTC(y, m - 1, d);
  return new Date(t - days * 86400000).toISOString().slice(0, 10);
}

export function yearStartIso(iso: string): string {
  return `${iso.slice(0, 4)}-01-01`;
}

export function daysBetweenIso(a: string, b: string): number {
  const pa = a.split('-').map(Number);
  const pb = b.split('-').map(Number);
  if (pa.length < 3 || pb.length < 3) return 0;
  const ta = Date.UTC(pa[0], pa[1] - 1, pa[2]);
  const tb = Date.UTC(pb[0], pb[1] - 1, pb[2]);
  return Math.round((tb - ta) / 86400000);
}

/**
 * Default preset: ITD when the position is younger than ~1Y vs as-of; otherwise 1Y.
 */
export function defaultDrilldownWindow(firstEntryDate: string | null, asOf: string): DrilldownWindow {
  if (!firstEntryDate) return '1y';
  if (daysBetweenIso(firstEntryDate, asOf) <= 370) return 'itd';
  return '1y';
}

export function resolveInceptionDate(
  ticker: string,
  position: Pick<Position, 'entry_date'>,
  positionHistory: PositionHistoryRow[],
  positionEvents: DashboardPositionEvent[]
): string | null {
  return resolveFirstEntryDate(ticker, position, positionEvents, positionHistory, null);
}

/**
 * Start date for a window preset, before clipping to performance range or first entry.
 */
export function windowStartForPreset(asOf: string, preset: DrilldownWindow, inceptionDate: string | null): string {
  if (preset === 'itd') {
    return inceptionDate ?? subtractIsoDays(asOf, 365 * 5);
  }
  if (preset === 'ytd') {
    const ys = yearStartIso(asOf);
    if (inceptionDate && inceptionDate > ys) return inceptionDate;
    return ys;
  }
  const days = preset === '1m' ? 30 : preset === '3m' ? 90 : preset === '1y' ? 365 : 90;
  const raw = subtractIsoDays(asOf, days);
  if (inceptionDate && raw < inceptionDate) return inceptionDate;
  return raw;
}

/** `priceRows` sorted ascending by date. */
export function closeOnOrAfter(
  priceRows: Array<{ date: string; close: number }>,
  iso: string
): number | null {
  const row = priceRows.find((r) => r.date >= iso);
  return row != null ? row.close : null;
}

function historyRowsForTicker(ticker: string, positionHistory: PositionHistoryRow[]): PositionHistoryRow[] {
  const t = ticker.toUpperCase();
  return positionHistory.filter((r) => String(r.ticker || '').toUpperCase() === t).sort((a, b) => a.date.localeCompare(b.date));
}

/**
 * Last known weight % at or before `iso` (0 if never held).
 */
export function weightPctOnOrBefore(
  iso: string,
  positionHistory: PositionHistoryRow[],
  ticker: string
): number {
  const rows = historyRowsForTicker(ticker, positionHistory);
  let last = 0;
  for (const r of rows) {
    if (r.date > iso) break;
    last = Number(r.weight_pct ?? 0);
  }
  return last;
}

/**
 * Forward-filled weight % for each trading day in `dates` (sorted ascending).
 */
export function forwardFillWeightsOnDates(
  dates: string[],
  positionHistory: PositionHistoryRow[],
  ticker: string
): number[] {
  const rows = historyRowsForTicker(ticker, positionHistory);
  const out: number[] = [];
  let j = 0;
  let last = 0;
  for (const d of dates) {
    while (j < rows.length && rows[j].date <= d) {
      last = Number(rows[j].weight_pct ?? 0);
      j++;
    }
    out.push(last);
  }
  return out;
}

export function filterActivityEvents(
  events: DashboardPositionEvent[],
  ticker: string,
  rangeStart: string,
  rangeEnd: string
): DashboardPositionEvent[] {
  const t = ticker.toUpperCase();
  return events
    .filter(
      (e) =>
        String(e.ticker || '').toUpperCase() === t &&
        e.event !== 'HOLD' &&
        e.date >= rangeStart &&
        e.date <= rangeEnd
    )
    .sort((a, b) => b.date.localeCompare(a.date) || a.event.localeCompare(b.event));
}

export function filterActivityEventsAscending(
  events: DashboardPositionEvent[],
  ticker: string,
  rangeStart: string,
  rangeEnd: string
): DashboardPositionEvent[] {
  const t = ticker.toUpperCase();
  return events
    .filter(
      (e) =>
        String(e.ticker || '').toUpperCase() === t &&
        e.event !== 'HOLD' &&
        e.date >= rangeStart &&
        e.date <= rangeEnd
    )
    .sort((a, b) => a.date.localeCompare(b.date) || a.event.localeCompare(b.event));
}

/**
 * Volume-weighted average entry from OPEN/ADD using event price or close on/after event date.
 */
export function computeAvgEntryFromAdds(
  eventsAsc: DashboardPositionEvent[],
  priceSorted: Array<{ date: string; close: number }>
): number | null {
  let num = 0;
  let den = 0;
  for (const e of eventsAsc) {
    if (e.event !== 'OPEN' && e.event !== 'ADD') continue;
    let addW: number | null = null;
    if (e.weight_change_pct != null && !Number.isNaN(Number(e.weight_change_pct))) {
      const d = Number(e.weight_change_pct);
      if (d > 0) addW = d;
    }
    if (addW == null && e.event === 'OPEN' && e.weight_pct != null && Number(e.weight_pct) > 0) {
      addW = Number(e.weight_pct);
    }
    if (addW == null || addW <= 0) continue;
    const px =
      e.price != null && !Number.isNaN(Number(e.price)) && Number(e.price) > 0
        ? Number(e.price)
        : closeOnOrAfter(priceSorted, e.date);
    if (px == null || px <= 0) continue;
    num += addW * px;
    den += addW;
  }
  return den > 0 ? num / den : null;
}

export type DrilldownChartRow = {
  date: string;
  close: number;
  weightPct: number;
  /** Events on this calendar date (may be multiple). */
  dayEvents: DashboardPositionEvent[];
};

export function buildDrilldownChartRows(
  priceSortedAsc: Array<{ date: string; close: number }>,
  positionHistory: PositionHistoryRow[],
  ticker: string,
  rangeStart: string,
  rangeEnd: string,
  eventsInRangeAsc: DashboardPositionEvent[]
): DrilldownChartRow[] {
  const prices = priceSortedAsc.filter((p) => p.date >= rangeStart && p.date <= rangeEnd);
  if (!prices.length) return [];
  const dates = prices.map((p) => p.date);
  const weights = forwardFillWeightsOnDates(dates, positionHistory, ticker);
  const byDate = new Map<string, DashboardPositionEvent[]>();
  for (const e of eventsInRangeAsc) {
    const list = byDate.get(e.date) ?? [];
    list.push(e);
    byDate.set(e.date, list);
  }
  return prices.map((p, i) => ({
    date: p.date,
    close: p.close,
    weightPct: weights[i] ?? 0,
    dayEvents: byDate.get(p.date) ?? [],
  }));
}

export type ContributionPptPoint = { date: string; dailyPp: number; cumPp: number };

/**
 * Daily contribution (ppt) from price returns × prior-day weight, cumulative over the window.
 */
export function buildPriceContributionPptSeries(
  priceSortedAsc: Array<{ date: string; close: number }>,
  positionHistory: PositionHistoryRow[],
  ticker: string,
  rangeStart: string,
  rangeEnd: string
): ContributionPptPoint[] {
  const prices = priceSortedAsc.filter((p) => p.date >= rangeStart && p.date <= rangeEnd).sort((a, b) => a.date.localeCompare(b.date));
  if (prices.length < 2) return [];
  const out: ContributionPptPoint[] = [{ date: prices[0].date, dailyPp: 0, cumPp: 0 }];
  let cum = 0;
  for (let i = 1; i < prices.length; i++) {
    const d0 = prices[i - 1].date;
    const d1 = prices[i].date;
    const p0 = prices[i - 1].close;
    const p1 = prices[i].close;
    const w = weightPctOnOrBefore(d0, positionHistory, ticker);
    let dailyPp = 0;
    if (p0 > 0 && p1 > 0) {
      const r = p1 / p0 - 1;
      dailyPp = (w / 100) * r * 100;
    }
    cum += dailyPp;
    out.push({ date: d1, dailyPp, cumPp: cum });
  }
  return out;
}

/** Net weight change over visible chart rows (first trading day vs last in window). */
export function netWeightChangeFromChartRows(rows: DrilldownChartRow[]): number | null {
  if (rows.length < 2) return null;
  return rows[rows.length - 1].weightPct - rows[0].weightPct;
}

/**
 * Effective [from, to] for fetch + display after padding and optional performance clip.
 */
export function resolveDrilldownRange(
  asOf: string,
  preset: DrilldownWindow,
  inceptionDate: string | null,
  performanceRange: { start: string; end: string } | null | undefined
): { fetchFrom: string; displayStart: string; displayEnd: string } {
  const displayEnd = performanceRange?.end ?? asOf;
  const presetStart = windowStartForPreset(displayEnd, preset, inceptionDate);
  let displayStart = presetStart;
  if (performanceRange && displayStart < performanceRange.start) {
    displayStart = performanceRange.start;
  }

  let fetchFrom = displayStart;
  if (inceptionDate) {
    const padded = subtractIsoDays(inceptionDate, DRILLDOWN_ENTRY_PADDING_DAYS);
    if (padded < fetchFrom) fetchFrom = padded;
  }
  if (performanceRange && fetchFrom < performanceRange.start) {
    fetchFrom = performanceRange.start;
  }

  return { fetchFrom, displayStart, displayEnd };
}
