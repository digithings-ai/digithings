/**
 * digiquant-runner Worker bindings (issue #4761).
 * Data-plane secrets are forwarded into the container. Auth tokens are not.
 */
export interface Env {
  RUNNER_AUTH_TOKEN?: string;
  RUNNER_CONTAINER: DurableObjectNamespace;
  R2_ACCOUNT_ID?: string;
  R2_BUCKET?: string;
  R2_ACCESS_KEY_ID?: string;
  R2_SECRET_ACCESS_KEY?: string;
  CORE_POSTGRES_URI?: string;
  CORE_SUPABASE_URL?: string;
  CORE_SUPABASE_SERVICE_KEY?: string;
  CLOUDFLARE_EMAIL_API_TOKEN?: string;
  CLOUDFLARE_ACCOUNT_ID?: string;
  NOTIFY_FROM?: string;
  DIGIQUANT_RUNNER_GIT_SHA?: string;
}

/** Container envVars whitelist. Omits RUNNER_AUTH_TOKEN and provider keys.
 * Execution-probe mail names may be empty. No FRED key. */
export function dataPlaneEnv(env: Env): Record<string, string> {
  return {
    R2_ACCOUNT_ID: env.R2_ACCOUNT_ID ?? "",
    R2_BUCKET: env.R2_BUCKET ?? "",
    R2_ACCESS_KEY_ID: env.R2_ACCESS_KEY_ID ?? "",
    R2_SECRET_ACCESS_KEY: env.R2_SECRET_ACCESS_KEY ?? "",
    CORE_POSTGRES_URI: env.CORE_POSTGRES_URI ?? "",
    CORE_SUPABASE_URL: env.CORE_SUPABASE_URL ?? "",
    CORE_SUPABASE_SERVICE_KEY: env.CORE_SUPABASE_SERVICE_KEY ?? "",
    CLOUDFLARE_EMAIL_API_TOKEN: env.CLOUDFLARE_EMAIL_API_TOKEN ?? "",
    CLOUDFLARE_ACCOUNT_ID: env.CLOUDFLARE_ACCOUNT_ID ?? "",
    NOTIFY_FROM: env.NOTIFY_FROM ?? "",
    DIGIQUANT_RUNNER_GIT_SHA: env.DIGIQUANT_RUNNER_GIT_SHA ?? "",
  };
}
