import type { DashboardPositionEvent } from './types';

export type RawPositionEventLike = {
  date: string;
  ticker: string;
  event: DashboardPositionEvent['event'];
  weight_pct: number | string | null;
  prev_weight_pct: number | string | null;
  price: number | string | null;
  thesis_id: string | null;
  reason: string | null;
};

function n(value: number | string | null): number | null {
  if (value == null) return null;
  const num = Number(value);
  return Number.isNaN(num) ? null : num;
}

export function normalizePositionEvent(row: RawPositionEventLike): DashboardPositionEvent {
  const weight = n(row.weight_pct);
  const rawPrev = n(row.prev_weight_pct);
  const prev = row.event === 'OPEN' && rawPrev == null && weight != null ? 0 : rawPrev;

  return {
    date: row.date,
    ticker: row.ticker,
    event: row.event,
    weight_pct: weight,
    prev_weight_pct: prev,
    weight_change_pct: weight != null && prev != null ? weight - prev : null,
    price: n(row.price),
    thesis_id: row.thesis_id ?? null,
    reason: row.reason ?? null,
  };
}
