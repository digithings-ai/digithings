/**
 * Prices-live environment seam.
 *
 * The edge function read `Deno.env.get(...)`; a module worker reads `env`.
 * Both are replaced here by ONE seam — `envGet(env, key)` over a plain record
 * — so the ported logic is identical under either runtime and every secret
 * lookup is injectable in tests (no global mutation, no ambient state).
 *
 * Nothing here declares a secret or a wrangler `[vars]` key: this leaf adds no
 * Cloudflare binding, so no production deploy change is implied. Chris sets the
 * bindings at cutover.
 */

export interface PricesLiveEnv {
  [key: string]: unknown;
}

/** String view of an env value; missing/blank reads as `undefined`. */
export function envGet(env: PricesLiveEnv | undefined, key: string): string | undefined {
  const value = env?.[key];
  if (typeof value !== "string") return undefined;
  const trimmed = value.trim();
  return trimmed.length > 0 ? trimmed : undefined;
}

/** First key that resolves, or `undefined` — the edge fallback chains. */
export function envFirst(env: PricesLiveEnv | undefined, keys: readonly string[]): string | undefined {
  for (const key of keys) {
    const value = envGet(env, key);
    if (value !== undefined) return value;
  }
  return undefined;
}
