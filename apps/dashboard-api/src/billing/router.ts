/**
 * Billing router — the module-worker transport for the three ported routes.
 *
 * This is the whole "Deno.serve" replacement: the edge functions each mounted
 * their own path, here one `fetch` handler dispatches on the pathname and 404s
 * everything else with the same `{ code, message }` body shape the routes use.
 *
 * NOT WIRED into `src/index.ts` on purpose. Mounting it is a cutover step that
 * needs the Stripe secrets bound on the worker, which is Chris's call — see
 * README.md. Exporting several names from this file is fine: the "entrypoint may
 * export only `default`" rule applies to the module `src/index.ts` hands to
 * workerd, not to every module in the bundle.
 */

import { jsonError } from "./http";
import { corsPreflight } from "./cors";
import {
  handleCreateCheckoutSession,
  handleCustomerPortal,
  handleStripeWebhook,
  type BillingDeps,
} from "./routes";
import type { BillingEnv } from "./env";

export const BILLING_PATHS = {
  stripeWebhook: "/stripe-webhook",
  customerPortal: "/customer-portal",
  createCheckoutSession: "/create-checkout-session",
} as const;

export type BillingPath = (typeof BILLING_PATHS)[keyof typeof BILLING_PATHS];

/** A module worker export shape: `{ fetch(request) }`. */
export interface BillingFetchHandler {
  fetch(request: Request): Promise<Response>;
}

/**
 * Builds the fetch handler for one worker's `env`. `deps` is injectable so a
 * host can share one `AdminDb`, and so tests can drive the routes without a
 * network.
 */
export function createBillingFetch(
  env: BillingEnv,
  deps?: BillingDeps,
): BillingFetchHandler {
  return {
    async fetch(request: Request): Promise<Response> {
      const path = new URL(request.url).pathname.replace(/\/+$/, "") || "/";
      // A preflight for an unrouted path is still answered with the billing CORS
      // headers, so a browser sees why the call failed rather than an opaque
      // router 404 with no allow headers.
      if (request.method === "OPTIONS") return corsPreflight();

      switch (path) {
        case BILLING_PATHS.stripeWebhook:
          return handleStripeWebhook(request, env, deps ?? {});
        case BILLING_PATHS.customerPortal:
          return handleCustomerPortal(request, env, deps ?? {});
        case BILLING_PATHS.createCheckoutSession:
          return handleCreateCheckoutSession(request, env, deps ?? {});
        default:
          return jsonError(404, "NOT_FOUND", `No billing route for ${path}`);
      }
    },
  };
}