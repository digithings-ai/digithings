/**
 * House movers. There is no `GET /movers`. Day moves come from allocation
 * marks plus market closes. A missing mark is an em dash, never a made-up percent.
 */
import { fetchMarketCloses, type MarketClose } from '@/lib/market-data';
import { getAllocations } from './client';

export const MISSING_MARK = '—';

export interface MoverInputRow {
  ticker: string;
  current_price: number | null;
  /** Worker mark lane. `unavailable` fails closed even if a number leaked in. */
  marks?: string | null;
  is_cash?: boolean;
}

export interface MoverRow {
  ticker: string;
  /** Null when the mark or the prior close is missing. Never zero as a stand-in. */
  dayPct: number | null;
  display: string;
}

export function isCashTicker(row: MoverInputRow): boolean {
  return row.is_cash === true || row.ticker.trim().toUpperCase() === 'CASH';
}

/** Close on the session before the latest close for `ticker`. */
export function priorClose(closes: readonly MarketClose[], ticker: string): number | null {
  const rows = closes
    .filter((row) => row.ticker === ticker && Number.isFinite(row.close))
    .slice()
    .sort((a, b) => (a.date < b.date ? -1 : a.date > b.date ? 1 : 0));
  if (rows.length < 2) return null;
  return rows[rows.length - 2].close;
}

export function dayMovePct(mark: number | null, prior: number | null): number | null {
  if (mark === null || prior === null) return null;
  if (!Number.isFinite(mark) || !Number.isFinite(prior) || prior === 0) return null;
  return ((mark - prior) / prior) * 100;
}

export function formatDayMove(dayPct: number | null): string {
  if (dayPct === null || !Number.isFinite(dayPct)) return MISSING_MARK;
  const sign = dayPct > 0 ? '+' : '';
  return `${sign}${dayPct.toFixed(2)}%`;
}

function markIsMissing(row: MoverInputRow): boolean {
  if (row.marks === 'unavailable') return true;
  return row.current_price === null || !Number.isFinite(row.current_price);
}

/**
 * Sort by absolute day move, largest first. Rows without a percent stay in
 * the list, after the ranked names, and render {@link MISSING_MARK}.
 */
export function deriveMovers(
  rows: readonly MoverInputRow[],
  closes: readonly MarketClose[],
): MoverRow[] {
  const movers: MoverRow[] = [];
  for (const row of rows) {
    if (isCashTicker(row)) continue;
    const dayPct = markIsMissing(row) ? null : dayMovePct(row.current_price, priorClose(closes, row.ticker));
    movers.push({
      ticker: row.ticker,
      dayPct,
      display: formatDayMove(dayPct),
    });
  }
  movers.sort((a, b) => {
    if (a.dayPct === null && b.dayPct === null) return a.ticker.localeCompare(b.ticker);
    if (a.dayPct === null) return 1;
    if (b.dayPct === null) return -1;
    const byAbs = Math.abs(b.dayPct) - Math.abs(a.dayPct);
    if (byAbs !== 0) return byAbs;
    return a.ticker.localeCompare(b.ticker);
  });
  return movers;
}

function utcDay(isoDate: string, deltaDays: number): string {
  const [year, month, day] = isoDate.split('-').map((part) => Number(part));
  const utc = new Date(Date.UTC(year, month - 1, day));
  utc.setUTCDate(utc.getUTCDate() + deltaDays);
  return utc.toISOString().slice(0, 10);
}

/**
 * Live derivation: `GET /allocations` plus `GET /v1/market/closes`.
 * Unset market data yields em dashes, not estimated percents.
 */
export async function loadMovers(query?: { asOf?: string; from?: string; to?: string }): Promise<MoverRow[]> {
  const book = await getAllocations({ asOf: query?.asOf, includeMarks: true });
  const rows = book.data.rows.map((row) => ({
    ticker: row.ticker,
    current_price: row.current_price,
    marks: row.marks,
  }));
  const tickers = rows.filter((row) => !isCashTicker(row)).map((row) => row.ticker);
  const to = query?.to ?? book.data.book_as_of ?? new Date().toISOString().slice(0, 10);
  const from = query?.from ?? utcDay(to, -14);
  const closes = tickers.length > 0 ? await fetchMarketCloses(tickers, from, to) : [];
  return deriveMovers(rows, closes);
}
