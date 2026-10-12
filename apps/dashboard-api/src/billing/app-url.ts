/**
 * App URL helpers — a port of
 * `digiquant/supabase/functions/_shared/app-url.ts`.
 *
 * Same normalisation rules as the edge version, because the redirect the
 * dashboard lands on must not change at the cutover: strip trailing slashes,
 * then strip ONE known base suffix so `/dashboard` and `/olympus` deployment
 * prefixes collapse to the public origin.
 *
 * Only `publicAlpacaOauthClientId` read the environment, and it read it in a
 * default parameter; the port takes the record explicitly. Nothing in the
 * three ported routes calls it — it is carried for contract parity only.
 */

import { envFirst, type BillingEnv } from "./env";

export const ALPACA_OAUTH_CALLBACK_PATH = "/dashboard/settings/brokers/callback/";
export const SETTINGS_PATH = "/dashboard/settings/";
const KNOWN_BASE_SUFFIXES = ["/dashboard", "/olympus"];

export function publicAppOrigin(raw: string | null | undefined): string {
  let origin = (raw ?? "").trim();
  while (origin.endsWith("/")) origin = origin.slice(0, -1);
  const lower = origin.toLowerCase();
  for (const suffix of KNOWN_BASE_SUFFIXES) {
    if (lower.endsWith(suffix)) {
      origin = origin.slice(0, origin.length - suffix.length);
      break;
    }
  }
  return origin;
}

export function pinnedAlpacaRedirectUriFromOrigin(appUrl: string): string {
  const origin = publicAppOrigin(appUrl);
  if (!origin) throw new Error("APP_URL unset");
  return `${origin}${ALPACA_OAUTH_CALLBACK_PATH}`;
}

/**
 * Where Stripe returns the user after checkout / cancel / portal. `checkout`
 * is only present on the checkout-session routes; the portal route calls this
 * with no `checkout` and gets the plain billing tab.
 */
export function settingsBillingReturnUrl(
  appUrl: string,
  checkout?: "success" | "cancel",
): string {
  const origin = publicAppOrigin(appUrl);
  if (!origin) throw new Error("APP_URL unset");
  const params = new URLSearchParams({ tab: "billing" });
  if (checkout) params.set("checkout", checkout);
  return `${origin}${SETTINGS_PATH}?${params.toString()}`;
}

export function publicAlpacaOauthClientId(raw: string | null | undefined, env: BillingEnv): string {
  const resolved =
    raw ?? envFirst(env, ["ALPACA_OAUTH_CLIENT_ID", "NEXT_PUBLIC_ALPACA_OAUTH_CLIENT_ID"]) ?? "";
  return resolved.trim();
}