import type { DashboardPositionEvent, Position, PositionHistoryRow } from './types';

/**
 * Earliest meaningful date for a position: OPEN event, then entry_date, then first history row.
 * When `asOf` is set, OPEN dates after `asOf` are ignored (bad pipeline data would otherwise push
 * `rangeStart` past available prices and yield empty charts).
 */
export function resolveFirstEntryDate(
  ticker: string,
  position: Pick<Position, 'entry_date'>,
  positionEvents: DashboardPositionEvent[],
  positionHistory: PositionHistoryRow[],
  asOf?: string | null
): string | null {
  const t = ticker.toUpperCase();
  const cap = asOf?.trim() || null;
  const openDates = positionEvents
    .filter((e) => e.ticker.toUpperCase() === t && e.event === 'OPEN')
    .map((e) => e.date)
    .filter((d) => !cap || d <= cap)
    .sort();
  if (openDates.length) return openDates[0];
  if (position.entry_date) return position.entry_date;
  const hist = positionHistory
    .filter((h) => h.ticker.toUpperCase() === t)
    .map((h) => h.date)
    .filter((d) => !cap || d <= cap)
    .sort();
  return hist.length ? hist[0] : null;
}
