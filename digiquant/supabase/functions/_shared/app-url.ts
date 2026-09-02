/**
 * Public origin + dashboard path helpers for Edge Functions.
 *
 * ``APP_URL`` / ``NEXT_PUBLIC_APP_URL`` must be the **site origin**
 * (``https://digiquant.io``), never ``http://127.0.0.1`` and never a path
 * that already includes ``/dashboard`` or the retired ``/olympus`` prefix
 * (that would double the basePath). Checkout return URLs and the Alpaca
 * OAuth redirect_uri both append ``/dashboard/...`` so they match the
 * static Pages export.
 */

export const ALPACA_OAUTH_CALLBACK_PATH = "/dashboard/settings/brokers/callback/";
export const SETTINGS_PATH = "/dashboard/settings/";

const KNOWN_BASE_SUFFIXES = ["/dashboard", "/olympus"] as const;

export function publicAppOrigin(raw: string): string {
  let base = raw.trim().replace(/\/+$/, "");
  const lower = base.toLowerCase();
  for (const suffix of KNOWN_BASE_SUFFIXES) {
    if (lower.endsWith(suffix)) {
      base = base.slice(0, -suffix.length);
      break;
    }
  }
  return base;
}

export function pinnedAlpacaRedirectUriFromOrigin(appUrl: string): string {
  const origin = publicAppOrigin(appUrl);
  if (!origin) {
    throw new Error("APP_URL unset");
  }
  return `${origin}${ALPACA_OAUTH_CALLBACK_PATH}`;
}

export function settingsBillingReturnUrl(
  appUrl: string,
  checkout?: "success" | "cancel",
): string {
  const origin = publicAppOrigin(appUrl);
  if (!origin) {
    throw new Error("APP_URL unset");
  }
  const params = new URLSearchParams();
  params.set("tab", "billing");
  if (checkout !== undefined) {
    params.set("checkout", checkout);
  }
  return `${origin}${SETTINGS_PATH}?${params.toString()}`;
}

/**
 * Public Alpaca OAuth client id for the authorize URL.
 * Never reads ``ALPACA_OAUTH_CLIENT_SECRET``.
 */
export function publicAlpacaOauthClientId(raw?: string): string {
  const value =
    raw ??
    Deno.env.get("ALPACA_OAUTH_CLIENT_ID") ??
    Deno.env.get("NEXT_PUBLIC_ALPACA_OAUTH_CLIENT_ID") ??
    "";
  return value.trim();
}
