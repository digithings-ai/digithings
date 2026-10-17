/**
 * Prices-live data access.
 *
 * The edge function reached Supabase through `SupabaseClient` from
 * `@supabase/supabase-js`. That dependency does not exist in this worker, so
 * the port deliberately does NOT vendor a query-builder client.
 *
 * It defines `PricesLiveDb` — the narrow set of operations the handler
 * actually performs — and one PostgREST-over-`fetch` implementation. Every
 * semantic the edge version relied on is preserved explicitly:
 *
 *  - the claim is the atomic `claim_prices_live_refresh` RPC and only
 *    `data === true` counts (fail closed on error/throw/non-true);
 *  - the ticker read degrades to majors-only when the view hiccups;
 *  - the upsert resolves to DO UPDATE (`resolution=merge-duplicates` with
 *    `on_conflict=ticker`); `ignoreDuplicates` must never become true or
 *    every ticker freezes at its first price with a healthy-looking "ok".
 *
 * Supabase stays live and untouched (2-week rollback). This module is the only
 * thing that talks to it, so a later D1-backed leaf replaces this file and
 * leaves the handler untouched.
 */

import { envFirst, type PricesLiveEnv } from "./env";
import type { PriceRow } from "./market";

export interface PricesLiveDb {
  /** Atomic lease claim; `true` only when this run won the window. */
  claimRefresh(minAgeSeconds: number): Promise<boolean>;
  /** Distinct portfolio tickers, or `null` when the view hiccups. */
  listPortfolioTickers(): Promise<string[] | null>;
  /** Upserts rows keyed on ticker; returns `"ok"` or the error message. */
  upsertPrices(rows: PriceRow[]): Promise<string>;
}

export class AdminNotConfiguredError extends Error {
  constructor() {
    super("Supabase admin env not configured");
    this.name = "AdminNotConfiguredError";
  }
}

/** Every lookup the handler makes, including the edge fallback chains. */
export function supabaseBase(env: PricesLiveEnv): { url: string; serviceKey: string } {
  const url = envFirst(env, ["SUPABASE_URL", "CORE_SUPABASE_URL"]);
  const serviceKey = envFirst(env, ["SUPABASE_SERVICE_ROLE_KEY", "CORE_SUPABASE_SERVICE_KEY"]);
  if (!url || !serviceKey) throw new AdminNotConfiguredError();
  return { url: url.replace(/\/+$/, ""), serviceKey };
}

export function createPostgrestPricesLive(env: PricesLiveEnv): PricesLiveDb {
  const { url, serviceKey } = supabaseBase(env);

  async function rest(
    path: string,
    init: { method?: string; body?: unknown; headers?: Record<string, string> } = {},
  ): Promise<{ status: number; code: string | null; message: string; data: unknown }> {
    const headers: Record<string, string> = {
      apikey: serviceKey,
      Authorization: `Bearer ${serviceKey}`,
      "Content-Type": "application/json",
      ...init.headers,
    };
    const res = await fetch(`${url}/rest/v1/${path}`, {
      method: init.method ?? "GET",
      headers,
      body: init.body === undefined ? undefined : JSON.stringify(init.body),
    });
    const text = await res.text();
    let data: unknown = null;
    let code: string | null = null;
    let message = text;
    if (text.length > 0) {
      try {
        data = JSON.parse(text);
        if (Array.isArray(data)) {
          code = null;
          message = text;
        } else if (data && typeof data === "object") {
          code = (data as { code?: string }).code ?? null;
          message = (data as { message?: string }).message ?? text;
        }
      } catch {
        data = null;
      }
    }
    return { status: res.status, code, message, data };
  }

  return {
    async claimRefresh(minAgeSeconds) {
      try {
        // Cast the AWAITED value, never the builder: the only thing that may
        // be read is the resolved scalar, and only `=== true` wins.
        const res = await rest("rpc/claim_prices_live_refresh", {
          method: "POST",
          body: { min_age_seconds: minAgeSeconds },
        });
        if (res.status >= 400) {
          console.error(`prices-live: refresh claim failed: ${res.message}`);
          return false;
        }
        return res.data === true;
      } catch (err) {
        console.error(
          `prices-live: refresh claim threw: ${err instanceof Error ? err.message : String(err)}`,
        );
        return false;
      }
    },

    async listPortfolioTickers() {
      const res = await rest(`public_portfolio_positions?select=ticker`);
      if (res.status >= 400 || !Array.isArray(res.data)) {
        return null;
      }
      return (res.data as Array<{ ticker: unknown }>)
        .map((row) => row.ticker)
        .filter((t): t is string => typeof t === "string");
    },

    async upsertPrices(rows) {
      // `ignoreDuplicates` stays false: this MUST resolve to DO UPDATE.
      // Prefer merge-duplicates + on_conflict=ticker is the PostgREST form of
      // supabase-js `upsert(rows, { onConflict: "ticker" })`.
      const res = await rest(`prices_live?on_conflict=ticker`, {
        method: "POST",
        headers: { Prefer: "resolution=merge-duplicates,return=minimal" },
        body: rows,
      });
      if (res.status >= 400) return res.message;
      return "ok";
    },
  };
}
