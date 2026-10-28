/**
 * Prices-live router — the module-worker transport for the ported route.
 *
 * This is the whole "Deno.serve" replacement: the edge function mounted its
 * own path, here one `fetch` handler dispatches on the pathname and 404s
 * everything else with a plain body. The market-closed / dormant / skipped
 * shapes all live in `routes.ts`; this file only owns the path table.
 *
 * `src/index.ts` mounts it only when `PRICES_LIVE_WORKER_ROUTES` is `"1"`
 * (Supabase exit S4, DIG-2887); the edge function and pg_cron stay the
 * serving path until then. On the worker the refresh is a cron call, not a
 * public one: `POST /prices-live` needs `Authorization: Bearer
 * $PRICES_LIVE_CRON_TOKEN` and refuses when that secret is unset.
 * `GET /prices-live/quotes` reads the KV snapshot (public quotes, the same
 * data the Realtime channel broadcast) and answers 404 on the Supabase
 * backend. Exporting several names
 * from this file is fine: the "entrypoint may export only `default`" rule
 * applies to the module `src/index.ts` hands to workerd, not to every module
 * in the bundle.
 */

import { corsPreflight, withCors } from "./cors";
import { json } from "./http";
import { envGet } from "./env";
import { kvBinding, pricesLiveBackend, readQuotes } from "./kv-store";
import { handlePricesLive, type PricesLiveDeps } from "./routes";
import type { PricesLiveEnv } from "./env";

export const PRICES_LIVE_PATHS = {
  pricesLive: "/prices-live",
  quotes: "/prices-live/quotes",
} as const;

/** True only when `PRICES_LIVE_WORKER_ROUTES` is `"1"`: the edge function stays the default. */
export function pricesLiveWorkerRoutesOn(env: PricesLiveEnv | undefined): boolean {
  return envGet(env, "PRICES_LIVE_WORKER_ROUTES") === "1";
}

/** Constant-time compare so the token check does not leak a prefix by timing. */
function sameToken(a: string, b: string): boolean {
  const enc = new TextEncoder();
  const x = enc.encode(a);
  const y = enc.encode(b);
  let diff = x.length ^ y.length;
  for (let i = 0; i < Math.max(x.length, y.length); i++) diff |= (x[i] ?? 0) ^ (y[i] ?? 0);
  return diff === 0;
}

/** Fail closed: no configured token means no caller is authorized. */
export function cronAuthorized(request: Request, env: PricesLiveEnv | undefined): boolean {
  const want = envGet(env, "PRICES_LIVE_CRON_TOKEN");
  if (!want) return false;
  const header = request.headers.get("Authorization") ?? "";
  const match = /^Bearer\s+(.+)$/i.exec(header.trim());
  return match !== null && sameToken(match[1].trim(), want);
}

export type PricesLivePath = (typeof PRICES_LIVE_PATHS)[keyof typeof PRICES_LIVE_PATHS];

/** A module worker export shape: `{ fetch(request) }`. */
export interface PricesLiveFetchHandler {
  fetch(request: Request): Promise<Response>;
}

/**
 * Builds the fetch handler for one worker's `env`. `deps` is injectable so
 * tests can drive the route without a network.
 */
export function createPricesLiveFetch(
  env: PricesLiveEnv,
  deps?: PricesLiveDeps,
): PricesLiveFetchHandler {
  return {
    async fetch(request: Request): Promise<Response> {
      const path = new URL(request.url).pathname.replace(/\/+$/, "") || "/";
      if (request.method === "OPTIONS") return corsPreflight();
      switch (path) {
        case PRICES_LIVE_PATHS.pricesLive:
          if (request.method !== "POST")
            return withCors(json({ error: "method not allowed" }, 405));
          if (!cronAuthorized(request, env)) return withCors(json({ error: "unauthorized" }, 401));
          return withCors(await handlePricesLive(request, env, deps ?? {}));
        case PRICES_LIVE_PATHS.quotes: {
          if (request.method !== "GET") return withCors(json({ error: "method not allowed" }, 405));
          const kv = pricesLiveBackend(env) === "kv" ? kvBinding(env) : null;
          if (!kv) return withCors(json({ error: "not found" }, 404));
          return withCors(json({ ...(await readQuotes(kv)) }));
        }
        default:
          return withCors(json({ error: "not found" }, 404));
      }
    },
  };
}
