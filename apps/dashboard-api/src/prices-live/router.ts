/**
 * Prices-live router — the module-worker transport for the ported route.
 *
 * This is the whole "Deno.serve" replacement: the edge function mounted its
 * own path, here one `fetch` handler dispatches on the pathname and 404s
 * everything else with a plain body. The market-closed / dormant / skipped
 * shapes all live in `routes.ts`; this file only owns the path table.
 *
 * NOT WIRED into `src/index.ts` on purpose. Mounting it is a cutover step
 * that needs the Finnhub secret and the Supabase service-role key bound on
 * the worker, which is Chris's call — see README.md. Exporting several names
 * from this file is fine: the "entrypoint may export only `default`" rule
 * applies to the module `src/index.ts` hands to workerd, not to every module
 * in the bundle.
 */

import { corsPreflight, withCors } from "./cors";
import { json } from "./http";
import { handlePricesLive, type PricesLiveDeps } from "./routes";
import type { PricesLiveEnv } from "./env";

export const PRICES_LIVE_PATHS = {
  pricesLive: "/prices-live",
} as const;

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
          return withCors(await handlePricesLive(request, env, deps ?? {}));
        default:
          return withCors(json({ error: "not found" }, 404));
      }
    },
  };
}
