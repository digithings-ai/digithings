/**
 * DigiQuant API client — the dashboard-api worker (apps/dashboard-api,
 * CONTRACT.md §6). Every data block binds to one route here.
 */
export type Envelope<T> = {
  data: T;
  as_of: string | null;
  provenance: { source: string; marks: 'stored' | 'market_api' | 'unavailable' };
};

export type BookRow = {
  ticker: string;
  scaled_weight_pct: number;
  entry_price: number | null;
  current_price: number | null;
  unrealized_pct: number | null;
};

export type Book = { book_as_of: string | null; rows: BookRow[] };

const base = () => (process.env.NEXT_PUBLIC_DQ_API_URL ?? '').replace(/\/+$/, '');

export async function dqGet<T>(route: string): Promise<Envelope<T>> {
  if (!base()) throw new Error('NEXT_PUBLIC_DQ_API_URL is not set');
  const res = await fetch(`${base()}${route}`);
  if (!res.ok) throw new Error(`${route} failed (${res.status})`);
  return (await res.json()) as Envelope<T>;
}

/** Fail closed to an em dash — never invent a number. */
export const pct = (v: number | null) => (v === null || !Number.isFinite(v) ? '—' : `${v.toFixed(2)}%`);
export const px = (v: number | null) => (v === null || !Number.isFinite(v) ? '—' : v.toFixed(2));
export const signed = (v: number | null) => (v === null || !Number.isFinite(v) ? '—' : `${v > 0 ? '+' : ''}${v.toFixed(2)}%`);
