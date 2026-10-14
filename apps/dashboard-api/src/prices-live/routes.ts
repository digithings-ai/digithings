/**
 * Prices-live route — a port of the `Deno.serve` handler in
 * `digiquant/supabase/functions/prices-live/index.ts`.
 *
 * Same wire contract, same check order, same bodies: dormant when the Finnhub
 * key is unset, market-closed outside extended US hours (unless forced),
 * not-claimed when the lease window belongs to another run, and the
 * open-market report otherwise. The dashboard and the pg_cron log scraping
 * parse those shapes today and must not need a client change at cutover.
 *
 * Two runtime differences, and only these:
 *
 * - `Deno.env.get` → the injected `env` record (`env.ts`), preserving the
 *   `SUPABASE_*` / `CORE_SUPABASE_*` fallback chains.
 * - `Deno.serve` → this exported handler (`router.ts` adapts it). The claim
 *   still runs after the market-hours gate (never consume a lease window on a
 *   run that was going to skip) and before the ticker query (a loser reads
 *   nothing).
 */

import { envFirst, type PricesLiveEnv } from "./env";
import { json } from "./http";
import {
  AdminNotConfiguredError,
  createPostgrestPricesLive,
  type PricesLiveDb,
} from "./admin";
import {
  fetchQuote as defaultFetchQuote,
  isExtendedUsMarketHours,
  MAJORS,
  MAX_SYMBOLS,
  MIN_REFRESH_SECONDS,
  quotedAtIso,
  sleep as defaultSleep,
  STAGGER_MS,
  type PriceRow,
  type QuoteOut,
} from "./market";

export interface PricesLiveDeps {
  /** Injected data layer; production builds the PostgREST one from `env`. */
  admin?: PricesLiveDb;
  /** Finnhub fetch; tests inject per-symbol scripted answers. */
  fetchQuoteFn?: (symbol: string, apiKey: string) => Promise<QuoteOut>;
  /** Run clock; tests pin market-open instants deterministically. */
  now?: () => Date;
  /** Stagger sleep; tests inject a no-op so the suite never waits. */
  sleep?: (ms: number) => Promise<void>;
}

export async function handlePricesLive(
  request: Request,
  env: PricesLiveEnv,
  deps: PricesLiveDeps = {},
): Promise<Response> {
  const at = (deps.now ?? (() => new Date()))();
  const sleep = deps.sleep ?? defaultSleep;
  const fetchQuoteFn = deps.fetchQuoteFn ?? defaultFetchQuote;

  // 1) Finnhub key gate — a misconfiguration guard (a dropped secret), not a
  //    dormant pre-launch state: the key has been set since 2026-07-13.
  const finnhubKey = envFirst(env, ["FINNHUB_API_KEY"]);
  if (!finnhubKey) {
    console.error("prices-live: FINNHUB_API_KEY not set — nothing fetched");
    return json({ dormant: true, at: at.toISOString() });
  }

  // 2) Market-hours gate. `{"force": true}` overrides THIS gate only: never
  //    the key gate above, never the claim below. A forced call inside the
  //    lease window still returns not-claimed — the accepted trade, not an
  //    oversight, because a force that skipped the claim would hand every
  //    anon-key holder the unbounded-fetch path back.
  const force = await request
    .json()
    .then((body: unknown) => (body as { force?: unknown } | null)?.force === true)
    .catch(() => false);
  if (!force && !isExtendedUsMarketHours(at)) {
    return json({ market: "closed", at: at.toISOString() });
  }

  // 3) Data layer. Missing Supabase env is a 500 with the edge's exact body.
  let admin = deps.admin;
  if (!admin) {
    try {
      admin = createPostgrestPricesLive(env);
    } catch (err) {
      if (err instanceof AdminNotConfiguredError) {
        console.error("prices-live: SUPABASE_URL / SUPABASE_SERVICE_ROLE_KEY missing");
        return json({ error: "supabase environment not configured" }, 500);
      }
      throw err;
    }
  }

  // 4) ATOMIC CLAIM — the rate guard. Fail closed: only `true` fetches.
  const claimed = await admin.claimRefresh(MIN_REFRESH_SECONDS);
  if (!claimed) {
    // 200, not 429: the scheduled caller did nothing wrong and pg_cron has no
    // retry to suppress.
    return json({ skipped: "not claimed", at: at.toISOString() });
  }

  // 5) Symbol set = distinct portfolio tickers + curated majors.
  const symbols = new Set<string>(MAJORS);
  const tickers = await admin.listPortfolioTickers();
  if (tickers === null) {
    // Majors still go out — a view hiccup should not blank the whole feed.
    console.error("prices-live: ticker query failed");
  } else {
    for (const raw of tickers) {
      const ticker = raw.trim().toUpperCase();
      // "CASH" is the portfolio's cash-sleeve pseudo-ticker, not a security —
      // Finnhub quotes it as Pathward Financial, which would put a fake mover
      // in the feed.
      if (ticker && ticker !== "CASH") symbols.add(ticker);
    }
  }
  const symbolList = [...symbols].sort().slice(0, MAX_SYMBOLS);
  if (symbols.size > MAX_SYMBOLS) {
    console.warn(`prices-live: ${symbols.size} symbols exceeds cap ${MAX_SYMBOLS}; truncated`);
  }

  // 6) Sequential fetch with a small stagger; per-symbol errors never abort.
  const quotes: Record<string, QuoteOut> = {};
  const errors: Record<string, string> = {};
  for (const [i, symbol] of symbolList.entries()) {
    if (i > 0) await sleep(STAGGER_MS);
    try {
      quotes[symbol] = await fetchQuoteFn(symbol, finnhubKey);
    } catch (err) {
      errors[symbol] = err instanceof Error ? err.message : String(err);
    }
  }

  // 7) Publish: ONE upsert into `public.prices_live`, keyed on ticker.
  //    `quoted_at` is Finnhub's tick time, `updated_at` is this run's start.
  //    `published` keeps the "ok" | <error string> shape so the cron log stays
  //    greppable, and carries the error VERBATIM: a scheduled run has no other
  //    diagnostic surface.
  let published = "skipped (no quotes)";
  const quoted = Object.keys(quotes).length;
  if (quoted > 0) {
    const rows: PriceRow[] = Object.entries(quotes).map(([ticker, q]) => ({
      ticker,
      price: q.c,
      change: q.d,
      change_pct: q.dp,
      quoted_at: quotedAtIso(q.t, at),
      updated_at: at.toISOString(),
    }));
    try {
      published = await admin.upsertPrices(rows);
    } catch (err) {
      published = err instanceof Error ? err.message : String(err);
    }
  }
  if (published !== "ok" && quoted > 0) {
    console.error(`prices-live: prices_live upsert failed: ${published}`);
  }

  return json({
    market: "open",
    forced: force,
    at: at.toISOString(),
    symbols: symbolList.length,
    quoted,
    failed: Object.keys(errors).length,
    errors,
    published,
  });
}
