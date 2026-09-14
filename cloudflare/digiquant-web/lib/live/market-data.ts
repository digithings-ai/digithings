/**
 * Browser client for the R2-backed market-data Worker (#4013) — benchmark leg.
 *
 * Serves `GET /v1/market/closes?tickers=A,B&from&to` → `{as_of, rows}`. The
 * benchmark read asks for one ticker and omits `to`, so the Worker's default
 * (`to = manifest.as_of`) bounds the series at the archive's own freshness.
 * digiquant.io is a static export, so `NEXT_PUBLIC_MARKET_DATA_URL` is inlined
 * at build time and the call runs client-side; when the var is unset
 * `fetchBenchmarkHistory` returns empty and `useLivePortfolio` keeps its
 * Supabase `price_history` read.
 */

function marketDataBaseUrl(): string {
  // Read per call, not at module scope: the export is inlined at build time, and
  // tests stub the env between imports.
  return (process.env.NEXT_PUBLIC_MARKET_DATA_URL ?? "").trim().replace(/\/+$/, "");
}

/** True when the benchmark leg should read from the market API. */
export function isMarketDataConfigured(): boolean {
  return marketDataBaseUrl().length > 0;
}

/** One close row exactly as `/v1/market/closes` shapes it. */
interface MarketCloseRow {
  date: string;
  ticker: string;
  close: number;
}

/**
 * Closes for `ticker` on/after `fromDate`, ascending (the Worker sorts).
 * Empty when unconfigured, and all-or-nothing on failure so a bad response
 * never reads as "the benchmark has no history".
 */
export async function fetchBenchmarkHistory(
  ticker: string,
  fromDate: string,
): Promise<{ date: string; price: number }[]> {
  const base = marketDataBaseUrl();
  if (!base) return [];
  try {
    const res = await fetch(
      `${base}/v1/market/closes?tickers=${encodeURIComponent(ticker)}&from=${fromDate}`,
    );
    if (!res.ok) {
      console.error("fetchBenchmarkHistory:", res.status);
      return [];
    }
    const body = (await res.json()) as { rows?: MarketCloseRow[] };
    return (body.rows ?? [])
      .map((row) => {
        const date = typeof row.date === "string" ? row.date : null;
        const price = Number(row.close);
        return date && Number.isFinite(price) ? { date, price } : null;
      })
      .filter((p): p is { date: string; price: number } => p !== null);
  } catch (err) {
    console.error("fetchBenchmarkHistory:", err);
    return [];
  }
}
