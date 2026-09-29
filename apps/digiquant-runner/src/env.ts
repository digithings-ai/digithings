/**
 * digiquant-runner Worker bindings (issue #4761).
 * Data-plane secrets are forwarded into the container. Auth tokens are not.
 */
export interface Env {
  RUNNER_AUTH_TOKEN?: string;
  /** issues:write on digithings-ai/digithings. Worker only — not a container env. */
  GH_ISSUE_TOKEN?: string;
  RUNNER_CONTAINER: DurableObjectNamespace;
  R2_ACCOUNT_ID?: string;
  R2_BUCKET?: string;
  R2_ACCESS_KEY_ID?: string;
  R2_SECRET_ACCESS_KEY?: string;
  FRED_API_KEY?: string;
  CORE_POSTGRES_URI?: string;
  CORE_SUPABASE_URL?: string;
  CORE_SUPABASE_SERVICE_KEY?: string;
  DIGIQUANT_RUNNER_GIT_SHA?: string;
}

/** Container envVars whitelist. Omits RUNNER_AUTH_TOKEN and GH_ISSUE_TOKEN. */
export function dataPlaneEnv(env: Env): Record<string, string> {
  return {
    R2_ACCOUNT_ID: env.R2_ACCOUNT_ID ?? "",
    R2_BUCKET: env.R2_BUCKET ?? "",
    R2_ACCESS_KEY_ID: env.R2_ACCESS_KEY_ID ?? "",
    R2_SECRET_ACCESS_KEY: env.R2_SECRET_ACCESS_KEY ?? "",
    FRED_API_KEY: env.FRED_API_KEY ?? "",
    CORE_POSTGRES_URI: env.CORE_POSTGRES_URI ?? "",
    CORE_SUPABASE_URL: env.CORE_SUPABASE_URL ?? "",
    CORE_SUPABASE_SERVICE_KEY: env.CORE_SUPABASE_SERVICE_KEY ?? "",
    DIGIQUANT_RUNNER_GIT_SHA: env.DIGIQUANT_RUNNER_GIT_SHA ?? "",
  };
}
