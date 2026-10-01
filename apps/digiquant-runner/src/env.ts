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
  /** House-run only. allocation-shadow's command allowlist stays empty. */
  DIGIQUANT_DIGIKEY_API_KEY?: string;
  OPENROUTER_API_KEY?: string;
  CHEAPERINFERENCE_API_KEY?: string;
  CHEAPERINFERENCE_API_BASE?: string;
  LANGSMITH_API_KEY?: string;
  /** Skip ledger on digithings-archive. Not forwarded into the container. */
  ARCHIVE?: HouseLedger;
}

/** R2 binding used for the house-run skip ledger. Same bucket as R2_BUCKET. */
export interface HouseLedger {
  head(key: string): Promise<unknown | null>;
  get(key: string): Promise<{ text(): Promise<string> } | null>;
  put(key: string, body: string): Promise<unknown>;
}

/** Container envVars whitelist. Omits RUNNER_AUTH_TOKEN.
 * House keys are present for the house-run allowlist; allocation-shadow drops them.
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
    DIGIQUANT_DIGIKEY_API_KEY: env.DIGIQUANT_DIGIKEY_API_KEY ?? "",
    OPENROUTER_API_KEY: env.OPENROUTER_API_KEY ?? "",
    CHEAPERINFERENCE_API_KEY: env.CHEAPERINFERENCE_API_KEY ?? "",
    CHEAPERINFERENCE_API_BASE: env.CHEAPERINFERENCE_API_BASE ?? "",
    LANGSMITH_API_KEY: env.LANGSMITH_API_KEY ?? "",
  };
}
