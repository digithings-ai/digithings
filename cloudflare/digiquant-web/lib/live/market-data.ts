/**
 * Browser client for the R2-backed market-data Worker (#4013/#4053) —
 * benchmark leg + Lane 1 seed.
 *
 * Serves `GET /v1/market/closes?tickers=A,B&from&to` → `{as_of, rows}`. Reads
 * omit `to`, so the Worker's default (`to = manifest.as_of`) bounds every
 * series at the archive's own freshness. digiquant.io is a static export, so
 * `NEXT_PUBLIC_MARKET_DATA_URL` is inlined at build time and the calls run
 * client-side; an unset var yields empty results — there is NO Supabase
 * fallback (#4053), so the var is required in prod (D5).
 */
import { seedRowToLive } from "./quote-transforms";
import type { LiveQuote } from "./types";

/** Worker cap: `/v1/market/closes` answers 400 above this (not a truncation). */
const MAX_TICKERS_PER_REQUEST = 25;

/** Calendar lookback for the Lane 1 seed: enough to hold the last two sessions. */
const SEED_LOOKBACK_DAYS = 14;

function marketDataBaseUrl(): string {
  // Read per call, not at module scope: the export is inlined at build time, and
  // tests stub the env between imports.
  return (process.env.NEXT_PUBLIC_MARKET_DATA_URL ?? "").trim().replace(/\/+$/, "");
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

/**
 * `from` for the Lane 1 seed request: `now` minus {@link SEED_LOOKBACK_DAYS}
 * (UTC). Stays in the past by construction, so the Worker's as_of-bounded `to`
 * always leaves a non-empty range for the latest closes to land in.
 */
export function seedWindowStart(now: Date = new Date()): string {
  return new Date(now.getTime() - SEED_LOOKBACK_DAYS * 86_400_000).toISOString().slice(0, 10);
}

/**
 * One-shot daily-close seed for Lane 1 (#4053, replaces the dropped public
 * price-latest view): for every symbol in the union of book tickers
 * and crypto product_ids, the LATEST close in `[fromDate, as_of]` plus its
 * prior-session move (computed from the preceding close in the same window,
 * so a seeded tape shows its real daily change instead of a flat 0%).
 *
 * Batched at the Worker's 25-ticker cap. Empty when unconfigured, and
 * all-or-nothing on a failed batch — a partial seed would silently pin some
 * symbols to stale closes and leave others blank.
 */
export async function seedFromWorker(symbols: string[], fromDate: string): Promise<LiveQuote[]> {
  const base = marketDataBaseUrl();
  if (!base || symbols.length === 0) return [];

  const rowsBySymbol = new Map<string, MarketCloseRow[]>();
  for (let i = 0; i < symbols.length; i += MAX_TICKERS_PER_REQUEST) {
    const batch = symbols.slice(i, i + MAX_TICKERS_PER_REQUEST);
    const query = `tickers=${batch.map((t) => encodeURIComponent(t)).join(",")}&from=${fromDate}`;
    try {
      const res = await fetch(`${base}/v1/market/closes?${query}`);
      if (!res.ok) {
        console.error("seedFromWorker:", res.status);
        return [];
      }
      const body = (await res.json()) as { rows?: MarketCloseRow[] };
      for (const row of body.rows ?? []) {
        const symbol = typeof row.ticker === "string" ? row.ticker.trim().toUpperCase() : "";
        if (!symbol) continue;
        const rows = rowsBySymbol.get(symbol) ?? [];
        rows.push(row);
        rowsBySymbol.set(symbol, rows);
      }
    } catch (err) {
      console.error("seedFromWorker:", err);
      return [];
    }
  }

  const seeds: LiveQuote[] = [];
  for (const [symbol, rows] of rowsBySymbol) {
    rows.sort((a, b) => a.date.localeCompare(b.date));
    const latest = rows[rows.length - 1];
    const prior = rows.length > 1 ? Number(rows[rows.length - 2].close) : null;
    const changePct =
      prior !== null && Number.isFinite(prior) && prior > 0
        ? ((Number(latest.close) - prior) / prior) * 100
        : 0;
    const seed = seedRowToLive({ ticker: symbol, close: latest.close, change_pct: changePct });
    if (seed) seeds.push(seed);
  }
  return seeds;
}
