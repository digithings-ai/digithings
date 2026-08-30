/**
 * Public origin + Olympus path helpers for Edge Functions.
 *
 * ``APP_URL`` / ``NEXT_PUBLIC_APP_URL`` must be the **site origin**
 * (``https://digiquant.io``), never ``http://127.0.0.1`` and never a path
 * that already includes ``/olympus`` (that would double the basePath).
 * Checkout return URLs and the Alpaca OAuth redirect_uri both append
 * ``/olympus/...`` so they match the static Pages export.
 */

export const ALPACA_OAUTH_CALLBACK_PATH = "/olympus/settings/brokers/callback/";
export const SETTINGS_PATH = "/olympus/settings/";

export function publicAppOrigin(raw: string): string {
  let base = raw.trim().replace(/\/+$/, "");
  const suffix = "/olympus";
  if (base.toLowerCase().endsWith(suffix)) {
    base = base.slice(0, -suffix.length);
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
