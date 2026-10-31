/**
 * Prices-live on Workers KV (Supabase exit S4, DIG-2887).
 *
 * A second `PricesLiveDb` beside the PostgREST one. The handler does not
 * change: it claims, lists tickers, fetches, and upserts through this
 * interface. `PRICES_LIVE_BACKEND = "kv"` picks this store; anything else
 * keeps the Supabase path, which stays the default until cutover.
 *
 * - Lease: one KV key holding the last claim time. KV is not atomic, so this
 *   is a best-effort window, not the Postgres row lock. It is enough because
 *   the only writer is the authenticated cron call (one per minute); the
 *   bearer gate in `router.ts` is what keeps anonymous callers off Finnhub.
 * - Quotes: one KV key holding `{ updated_at, rows: { TICKER: row } }`.
 *   An upsert merges by ticker, matching `on_conflict=ticker`.
 * - Tickers: `PRICES_LIVE_TICKERS` (comma list) when set. Otherwise the core
 *   view through PostgREST when Supabase is configured, otherwise none (the
 *   handler still quotes the majors).
 */

import { createPostgrestPricesLive, type PricesLiveDb } from "./admin";
import { envGet, type PricesLiveEnv } from "./env";
import type { PriceRow } from "./market";

/** The two KV methods this store uses; a real `KVNamespace` satisfies it. */
export interface PricesLiveKv {
  get(key: string): Promise<string | null>;
  put(key: string, value: string, options?: { expirationTtl?: number }): Promise<void>;
}

export const LEASE_KEY = "prices-live:lease:v1";
export const QUOTES_KEY = "prices-live:quotes:v1";

/** KV's minimum expirationTtl. */
const KV_MIN_TTL_SECONDS = 60;

export interface QuotesSnapshot {
  updated_at: string | null;
  rows: Record<string, PriceRow>;
}

export class KvNotBoundError extends Error {
  constructor() {
    super("PRICES_LIVE_KV binding missing");
    this.name = "KvNotBoundError";
  }
}

/** `"kv"` only when the flag says so; Supabase is the default. */
export function pricesLiveBackend(env: PricesLiveEnv | undefined): "kv" | "supabase" {
  return envGet(env, "PRICES_LIVE_BACKEND") === "kv" ? "kv" : "supabase";
}

export function kvBinding(env: PricesLiveEnv | undefined): PricesLiveKv | null {
  const kv = env?.PRICES_LIVE_KV as Partial<PricesLiveKv> | undefined;
  return kv && typeof kv.get === "function" && typeof kv.put === "function"
    ? (kv as PricesLiveKv)
    : null;
}

export async function readQuotes(kv: PricesLiveKv): Promise<QuotesSnapshot> {
  const raw = await kv.get(QUOTES_KEY);
  if (!raw) return { updated_at: null, rows: {} };
  try {
    const parsed = JSON.parse(raw) as Partial<QuotesSnapshot>;
    const rows =
      parsed.rows && typeof parsed.rows === "object" && !Array.isArray(parsed.rows)
        ? parsed.rows
        : {};
    return { updated_at: typeof parsed.updated_at === "string" ? parsed.updated_at : null, rows };
  } catch {
    return { updated_at: null, rows: {} };
  }
}

function tickersFromEnv(env: PricesLiveEnv): string[] | undefined {
  const raw = envGet(env, "PRICES_LIVE_TICKERS");
  if (raw === undefined) return undefined;
  return raw
    .split(",")
    .map((t) => t.trim())
    .filter((t) => t.length > 0);
}

export function createKvPricesLive(
  env: PricesLiveEnv,
  now: () => Date = () => new Date(),
): PricesLiveDb {
  const kv = kvBinding(env);
  if (!kv) throw new KvNotBoundError();

  return {
    async claimRefresh(minAgeSeconds) {
      try {
        const last = await kv.get(LEASE_KEY);
        const at = now();
        if (last) {
          const ageMs = at.getTime() - Date.parse(last);
          // An unparseable stamp reads as NaN and fails `>=`: fail closed.
          if (!(ageMs >= minAgeSeconds * 1000)) return false;
        }
        await kv.put(LEASE_KEY, at.toISOString(), {
          expirationTtl: Math.max(KV_MIN_TTL_SECONDS, Math.ceil(minAgeSeconds * 2)),
        });
        return true;
      } catch (err) {
        console.error(
          `prices-live: kv claim threw: ${err instanceof Error ? err.message : String(err)}`,
        );
        return false;
      }
    },

    async listPortfolioTickers() {
      const fromEnv = tickersFromEnv(env);
      if (fromEnv !== undefined) return fromEnv;
      try {
        return await createPostgrestPricesLive(env).listPortfolioTickers();
      } catch {
        // No Supabase configured: majors only, which the handler already adds.
        return [];
      }
    },

    async upsertPrices(rows) {
      try {
        const snapshot = await readQuotes(kv);
        let latest = snapshot.updated_at;
        for (const row of rows) {
          snapshot.rows[row.ticker] = row;
          if (!latest || row.updated_at > latest) latest = row.updated_at;
        }
        await kv.put(QUOTES_KEY, JSON.stringify({ updated_at: latest, rows: snapshot.rows }));
        return "ok";
      } catch (err) {
        return err instanceof Error ? err.message : "unknown error";
      }
    },
  };
}
