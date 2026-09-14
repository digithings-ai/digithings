/**
 * Browser client for the R2-backed market-data Worker (#4013).
 *
 * Serves `GET /v1/market/tickers` → `{as_of, tickers}` and
 * `GET /v1/market/closes?tickers=A,B&from&to` → `{as_of, rows}`. The dashboard
 * is a static export, so `NEXT_PUBLIC_MARKET_DATA_URL` is inlined at build time
 * and the calls run client-side; when the var is unset every function returns
 * empty and callers keep their Supabase read paths.
 */

/** One close row exactly as `/v1/market/closes` shapes it. */
export interface MarketClose {
  date: string;
  ticker: string;
  close: number;
}

/** Worker cap: `/v1/market/closes` answers 400 above this (not a truncation). */
const MAX_TICKERS_PER_REQUEST = 25;

function marketDataBaseUrl(): string {
  // Read per call, not at module scope: the export is inlined at build time, and
  // tests stub the env between imports.
  return (process.env.NEXT_PUBLIC_MARKET_DATA_URL ?? '').trim().replace(/\/+$/, '');
}

/** True when the dashboard should read prices from the market API. */
export function isMarketDataConfigured(): boolean {
  return marketDataBaseUrl().length > 0;
}

/** Ticker universe in the R2 archive; empty when unconfigured or on failure. */
export async function fetchMarketTickers(): Promise<string[]> {
  const base = marketDataBaseUrl();
  if (!base) return [];
  try {
    const res = await fetch(`${base}/v1/market/tickers`);
    if (!res.ok) {
      console.error('fetchMarketTickers:', res.status);
      return [];
    }
    const body = (await res.json()) as { tickers?: string[] };
    return body.tickers ?? [];
  } catch (err) {
    console.error('fetchMarketTickers:', err);
    return [];
  }
}

/**
 * Closes for `tickers` in the inclusive `[minDate, maxDate]` window.
 * Empty when unconfigured, and all-or-nothing on a failed batch so a missing
 * ticker never reads as "no data for that ticker".
 */
export async function fetchMarketCloses(
  tickers: string[],
  minDate: string,
  maxDate: string
): Promise<MarketClose[]> {
  const base = marketDataBaseUrl();
  if (!base || tickers.length === 0) return [];

  const rows: MarketClose[] = [];
  for (let i = 0; i < tickers.length; i += MAX_TICKERS_PER_REQUEST) {
    const batch = tickers.slice(i, i + MAX_TICKERS_PER_REQUEST);
    const query = `tickers=${batch.map((t) => encodeURIComponent(t)).join(',')}&from=${minDate}&to=${maxDate}`;
    try {
      const res = await fetch(`${base}/v1/market/closes?${query}`);
      if (!res.ok) {
        console.error('fetchMarketCloses:', res.status);
        return [];
      }
      const body = (await res.json()) as { rows?: MarketClose[] };
      rows.push(...(body.rows ?? []));
    } catch (err) {
      console.error('fetchMarketCloses:', err);
      return [];
    }
  }
  return rows;
}
