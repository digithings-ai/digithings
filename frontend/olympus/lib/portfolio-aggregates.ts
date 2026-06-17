import type { Position, PositionHistoryRow, Thesis } from './types';

/** Max distinct tickers in stacked history before merging the rest into `_other`. */
export const SLEEVE_TOP_N_TICKERS = 10;

export type SleeveStackMode = 'category' | 'thesis' | 'ticker';

function sleeveKey(row: PositionHistoryRow, mode: Exclude<SleeveStackMode, 'ticker'>): string {
  if (mode === 'thesis') return row.thesis_id || '_unlinked';
  if (row.ticker === 'CASH') return 'cash';
  return row.category || 'uncategorized';
}

/**
 * Per-ticker weights by date, then keep top N tickers by **peak single-day weight** over the window;
 * remaining names roll into `_other` each day.
 */
function buildTickerSleeveSeries(rows: PositionHistoryRow[]): {
  data: Array<Record<string, number | string>>;
  keys: string[];
} {
  const byDate = new Map<string, Map<string, number>>();
  for (const r of rows) {
    const t = r.ticker || '_unknown';
    if (!byDate.has(r.date)) byDate.set(r.date, new Map());
    const m = byDate.get(r.date)!;
    m.set(t, (m.get(t) ?? 0) + r.weight_pct);
  }
  const dates = [...byDate.keys()].sort();

  const peakByTicker = new Map<string, number>();
  for (const m of byDate.values()) {
    for (const [ticker, w] of m) {
      peakByTicker.set(ticker, Math.max(peakByTicker.get(ticker) ?? 0, w));
    }
  }
  const ranked = [...peakByTicker.entries()].sort((a, b) => b[1] - a[1]);
  const topSet = new Set(ranked.slice(0, SLEEVE_TOP_N_TICKERS).map(([t]) => t));
  const hasOther = ranked.length > SLEEVE_TOP_N_TICKERS;

  const keys = ranked.slice(0, SLEEVE_TOP_N_TICKERS).map(([t]) => t);
  if (hasOther) keys.push('_other');

  const data = dates.map((date) => {
    const row: Record<string, number | string> = { date };
    const m = byDate.get(date)!;
    let otherSum = 0;
    for (const [ticker, w] of m) {
      if (topSet.has(ticker)) {
        row[ticker] = Math.round(w * 1000) / 1000;
      } else {
        otherSum += w;
      }
    }
    if (hasOther) {
      row._other = Math.round(otherSum * 1000) / 1000;
    }
    for (const k of keys) {
      if (row[k] === undefined) row[k] = 0;
    }
    return row;
  });

  return { data, keys };
}

/** Stacked % weights by date for Recharts (one row per date, dynamic keys). */
export function buildSleeveStackSeries(
  rows: PositionHistoryRow[],
  mode: SleeveStackMode
): { data: Array<Record<string, number | string>>; keys: string[] } {
  if (mode === 'ticker') {
    return buildTickerSleeveSeries(rows);
  }

  const byDate = new Map<string, Map<string, number>>();
  const allKeys = new Set<string>();
  for (const r of rows) {
    const k = sleeveKey(r, mode);
    allKeys.add(k);
    if (!byDate.has(r.date)) byDate.set(r.date, new Map());
    const m = byDate.get(r.date)!;
    m.set(k, (m.get(k) ?? 0) + r.weight_pct);
  }
  const dates = [...byDate.keys()].sort();
  const keys = [...allKeys].sort((a, b) => {
    if (a === '_unlinked') return 1;
    if (b === '_unlinked') return -1;
    return a.localeCompare(b);
  });
  const data = dates.map((date) => {
    const row: Record<string, number | string> = { date };
    const m = byDate.get(date)!;
    for (const key of keys) {
      row[key] = Math.round((m.get(key) ?? 0) * 1000) / 1000;
    }
    return row;
  });
  return { data, keys };
}

export function tickerStackLabel(key: string): string {
  if (key === '_other') return 'Other';
  return key;
}

export function thesisStackLabel(key: string, theses: Thesis[]): string {
  if (key === '_unlinked') return 'Unlinked';
  const t = theses.find((x) => x.id === key);
  return t?.name ?? key;
}

export function categoryStackLabel(key: string): string {
  if (key === 'cash') return 'Cash';
  if (key === 'uncategorized') return 'Uncategorized';
  return key.replace(/_/g, ' ');
}

/** Weight % per thesis_id from holdings (live positions or a single history slice). */
export function aggregateWeightByThesis(
  positions: Pick<Position, 'weight_actual' | 'thesis_ids'>[]
): Map<string, number> {
  const m = new Map<string, number>();
  for (const p of positions) {
    const ids = p.thesis_ids?.length ? p.thesis_ids : ['_unlinked'];
    const share = (p.weight_actual ?? 0) / ids.length;
    for (const id of ids) {
      const k = id || '_unlinked';
      m.set(k, (m.get(k) ?? 0) + share);
    }
  }
  return m;
}
