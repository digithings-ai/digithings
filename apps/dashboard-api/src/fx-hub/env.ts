/**
 * FX Hub environment seam.
 *
 * The edge functions read `Deno.env.get(...)`; a module worker reads `env`.
 * Both are replaced here by one seam — `envGet` / `readApiKey` over a plain
 * record — so the ported logic is identical under either runtime and every
 * secret lookup is injectable in tests (no global mutation, no ambient state).
 *
 * Nothing here declares a secret or a wrangler `[vars]` key. The new-format
 * key dictionaries are read and never filled in from the legacy
 * `SUPABASE_ANON_KEY` / `SUPABASE_SERVICE_ROLE_KEY` variables.
 */

export interface FxHubEnv {
  [key: string]: unknown;
}

/** String view of an env value; missing/blank reads as `undefined`. */
export function envGet(env: FxHubEnv | undefined, key: string): string | undefined {
  const value = env?.[key];
  if (typeof value !== "string") return undefined;
  const trimmed = value.trim();
  return trimmed.length > 0 ? trimmed : undefined;
}

/**
 * Reads one new-format API key out of a JSON dictionary.
 * Returns null — never a partial value and never key material — when the
 * variable is absent, unparseable, or has no non-empty string under `keyName`.
 */
export function readApiKey(
  env: FxHubEnv | undefined,
  envVar: string,
  keyName = "default",
): string | null {
  const raw = envGet(env, envVar);
  if (!raw) return null;
  let parsed: unknown;
  try {
    parsed = JSON.parse(raw);
  } catch {
    return null;
  }
  if (parsed === null || typeof parsed !== "object" || Array.isArray(parsed)) return null;
  const key = (parsed as Record<string, unknown>)[keyName];
  return typeof key === "string" && key.length > 0 ? key : null;
}
