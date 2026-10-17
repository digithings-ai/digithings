/**
 * Prices-live market helpers — a verbatim port of the pure section of
 * `digiquant/supabase/functions/prices-live/index.ts`.
 *
 * No runtime calls here (`Deno`, `fetch`, `crypto`): the constants and the two
 * exported functions are identical under Deno and Workers, so the rate-guard
 * arithmetic and the timestamp handling cannot drift between the two lanes
 * while both are live.
 */

/** Curated majors quoted alongside portfolio tickers (indices, rates, FX, credit). */
export const MAJORS = ["SPY", "QQQ", "DIA", "IWM", "GLD", "TLT", "UUP", "EFA", "EEM", "HYG"];

/**
 * Hard cap on symbols per run. Coupled to MIN_REFRESH_SECONDS.
 *
 * 25 is not slack to be spent: two claims can land in one sliding 60 s window,
 * so the ceiling is 2 × MAX_SYMBOLS = 50 Finnhub calls/min against a 60/min
 * free tier. Live demand is at most 20 symbols, so nothing truncates today.
 * Raise this *and* re-derive MIN_REFRESH_SECONDS together, or coverage
 * silently shrinks. The two constants are one decision.
 */
export const MAX_SYMBOLS = 25;

/** Pause between sequential Finnhub calls so a run never bursts the rate limit. */
export const STAGGER_MS = 150;

/**
 * Minimum age of the refresh lease before another fetch may be claimed
 * (migration 064). Claims that fit in ANY sliding 60 s window are
 * floor(60 / MIN_REFRESH_SECONDS) + 1 = 2 at 50 s, so the real ceiling is
 * 2 × MAX_SYMBOLS = 50 calls/min. Keep strictly below pg_cron's 60 s period.
 */
export const MIN_REFRESH_SECONDS = 50;

/** Finnhub /quote response (https://finnhub.io/docs/api/quote). */
export interface FinnhubQuote {
  c: number; // current price
  d: number | null; // change
  dp: number | null; // percent change
  h: number;
  l: number;
  o: number;
  pc: number; // previous close
  t: number; // unix seconds
}

/** The per-symbol quote we keep from Finnhub — current price, change, % change, quote time. */
export interface QuoteOut {
  c: number;
  d: number | null;
  dp: number | null;
  t: number;
}

/**
 * One row of `public.prices_live` (migration 063).
 *
 * These column names are the wire contract with the browser: postgres_changes
 * ships the row verbatim, so renaming a column here does not break a build
 * anywhere — it silently blanks a field in the UI. Nullability mirrors the
 * table: Finnhub omits `d`/`dp` for some instruments, `price` and `quoted_at`
 * are NOT NULL.
 */
export interface PriceRow {
  ticker: string;
  price: number;
  change: number | null;
  change_pct: number | null;
  quoted_at: string;
  updated_at: string;
}

/**
 * Extended US market hours: 13:00–01:00 UTC, Mon–Fri (pre-market open through
 * after-hours close, DST-tolerant). The window wraps midnight UTC, so an 00:xx
 * timestamp belongs to the PREVIOUS day's session — 00:30 UTC Saturday is still
 * Friday evening in New York and counts as open.
 */
export function isExtendedUsMarketHours(now: Date): boolean {
  const hour = now.getUTCHours();
  const inWindow = hour >= 13 || hour < 1;
  if (!inWindow) return false;
  // 0=Sun … 6=Sat; before 01:00 UTC the session day is the previous UTC day.
  const sessionDay = hour < 1 ? (now.getUTCDay() + 6) % 7 : now.getUTCDay();
  return sessionDay >= 1 && sessionDay <= 5;
}

/**
 * Finnhub's `t` is unix **SECONDS**; `prices_live.quoted_at` is a
 * `timestamptz`. Hence the `* 1000`. A missing, non-finite, or OUT-OF-RANGE
 * `t` falls back to the run clock rather than throwing: `toISOString()` on a
 * malformed date raises `RangeError`, which would abort the whole handler and
 * throw away every good price over one bad timestamp. The range test is on the
 * constructed Date, not on `t`: any `t > 8.64e12` is finite and positive and
 * still throws.
 */
export function quotedAtIso(t: number | null | undefined, fallback: Date): string {
  if (typeof t !== "number" || !Number.isFinite(t) || t <= 0) return fallback.toISOString();
  const quoted = new Date(t * 1000);
  return Number.isNaN(quoted.getTime()) ? fallback.toISOString() : quoted.toISOString();
}

/** Default sleep; injectable so tests never wait on the stagger. */
export function sleep(ms: number): Promise<void> {
  return new Promise((resolve) => setTimeout(resolve, ms));
}

/** Finnhub quote fetch for one symbol. Throws on HTTP error or empty quote. */
export async function fetchQuote(symbol: string, apiKey: string): Promise<QuoteOut> {
  const url = `https://finnhub.io/api/v1/quote?symbol=${encodeURIComponent(symbol)}&token=${apiKey}`;
  const res = await fetch(url);
  if (!res.ok) {
    throw new Error(`Finnhub HTTP ${res.status}`);
  }
  const q = (await res.json()) as FinnhubQuote;
  // Finnhub returns c=0 (not an error) for unknown symbols — treat as a miss.
  if (typeof q?.c !== "number" || q.c <= 0) {
    throw new Error("empty quote (c<=0) — unknown symbol or no data");
  }
  return { c: q.c, d: q.d ?? null, dp: q.dp ?? null, t: q.t };
}
