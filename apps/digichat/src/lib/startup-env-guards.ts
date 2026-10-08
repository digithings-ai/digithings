/**
 * Startup environment guards. Each one fails closed — it throws instead of
 * degrading — so a misconfigured deployment is a loud boot failure rather than a
 * confusing one that only shows up as a broken login at request time.
 *
 * Kept dependency-free so every startup entry point (`src/instrumentation.ts`,
 * `src/auth.ts`) can call it without pulling in Next.js or Auth.js.
 */

/**
 * True when the dev password provider is switched on. Trimmed so a value like
 * `"1\r"` from a CRLF `.env` file still counts as on.
 */
export function isDevAuthEnabled(
  env: NodeJS.ProcessEnv | Record<string, string | undefined> = process.env,
): boolean {
  return env.DIGICHAT_DEV_AUTH?.trim() === "1";
}

/**
 * Throw when `NODE_ENV=production` and `DIGICHAT_DEV_AUTH=1`.
 *
 * The dev password provider compares against `DIGICHAT_DEV_PASSWORD` and falls
 * back to the literal string `dev` when that variable is empty or unset, then
 * issues a real session for `dev@digichat.local`. A credentials provider cannot
 * refuse on its own: `NODE_ENV` is a property of the build, not something it
 * can read per request, so the refusal belongs at startup next to the flag it
 * defends. Refusing silently would turn a deployment mistake into a login
 * nobody can explain.
 *
 * Call this at every entry point that can register the provider, and before
 * anything else runs — this is the earliest point at which the mistake is still
 * cheap to diagnose.
 */
export function assertDevAuthDisabledInProduction(
  env: NodeJS.ProcessEnv | Record<string, string | undefined> = process.env,
): void {
  if (env.NODE_ENV !== "production") return;
  if (!isDevAuthEnabled(env)) return;
  throw new Error(
    "digichat refused to start: NODE_ENV is production and DIGICHAT_DEV_AUTH is 1. " +
      "The dev password provider is for local development only: it accepts " +
      "DIGICHAT_DEV_PASSWORD, falls back to the literal password \"dev\" when that " +
      "variable is unset, and issues a real session for it. " +
      "Remove DIGICHAT_DEV_AUTH (and DIGICHAT_DEV_PASSWORD) from the production environment.",
  );
}
