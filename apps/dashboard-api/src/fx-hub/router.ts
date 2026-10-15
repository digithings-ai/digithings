/**
 * FX Hub router — the module-worker transport for the two ported functions.
 *
 * This is the `Deno.serve` replacement: one `fetch` handler dispatches on
 * the pathname. The status codes live in the handlers; this file only owns
 * the path table.
 *
 * NOT WIRED into `src/index.ts` on purpose. Mounting it is a cutover step
 * that needs the key dictionaries and the sync secret bound on the worker.
 * See README.md.
 */

import type { FxHubEnv } from "./env";
import { handleFxHubGrantSync } from "./grant-sync";
import { json } from "./http";
import { handleFxHubSession } from "./session";

export const FX_HUB_PATHS = {
  session: "/fx-hub-session",
  grantSync: "/fx-hub-grant-sync",
} as const;

export type FxHubPath = (typeof FX_HUB_PATHS)[keyof typeof FX_HUB_PATHS];

/** A module worker export shape: `{ fetch(request) }`. */
export interface FxHubFetchHandler {
  fetch(request: Request): Promise<Response>;
}

/** Builds the fetch handler for one worker's `env`. */
export function createFxHubFetch(env: FxHubEnv): FxHubFetchHandler {
  return {
    async fetch(request: Request): Promise<Response> {
      const path = new URL(request.url).pathname.replace(/\/+$/, "") || "/";
      switch (path) {
        case FX_HUB_PATHS.session:
          return handleFxHubSession(request, env);
        case FX_HUB_PATHS.grantSync:
          return handleFxHubGrantSync(request, env);
        default:
          return json({ ok: false, code: "NOT_FOUND" }, 404);
      }
    },
  };
}
