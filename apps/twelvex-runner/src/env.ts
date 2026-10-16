/**
 * twelvex-runner bindings.
 * Data-plane secrets are forwarded into the container. Auth tokens are not.
 */
export interface Env {
  /** Bearer required on POST /run/*. Never forwarded into the container. */
  RUNNER_AUTH_TOKEN?: string;
  /** Issues read/write on digithings-ai/twelve-x. Never forwarded. */
  GH_ISSUES_TOKEN?: string;
  /** "1" asks the container to skip the real command. Default "0". */
  DRY_RUN?: string;
  TWELVEX_CONTAINER: DurableObjectNamespace;
  PRIMEMARKET_SESSION_TOKEN?: string;
  TWELVEX_SUPABASE_SERVICE_KEY?: string;
  TWELVEX_SUPABASE_URL?: string;
}

/** Container envVars whitelist. Omits RUNNER_AUTH_TOKEN and GH_ISSUES_TOKEN. */
export function dataPlaneEnv(env: Env): Record<string, string> {
  return {
    PRIMEMARKET_SESSION_TOKEN: env.PRIMEMARKET_SESSION_TOKEN ?? "",
    TWELVEX_SUPABASE_SERVICE_KEY: env.TWELVEX_SUPABASE_SERVICE_KEY ?? "",
    TWELVEX_SUPABASE_URL: env.TWELVEX_SUPABASE_URL ?? "",
    DRY_RUN: env.DRY_RUN === "1" ? "1" : "0",
  };
}
