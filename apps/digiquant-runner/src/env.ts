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
  DIGI_OTEL_HEADERS?: string;
  /** Skip ledger on digithings-archive. Not forwarded into the container. */
  ARCHIVE?: HouseLedger;
}

/** R2 binding used for the house-run skip ledger. Same bucket as R2_BUCKET. */
export interface HouseLedger {
  head(key: string): Promise<unknown | null>;
  get(key: string): Promise<{ text(): Promise<string> } | null>;
  put(key: string, body: string): Promise<unknown>;
}

/** Names whose value may be forwarded empty. The execution-probe mail path
 * reads them as optional, so an unset binding must still arrive. */
const MAIL_ENV_NAMES = [
  "CLOUDFLARE_EMAIL_API_TOKEN",
  "CLOUDFLARE_ACCOUNT_ID",
  "NOTIFY_FROM",
] as const;

/** Container envVars whitelist. Omits RUNNER_AUTH_TOKEN.
 * House keys are present for the house-run allowlist; allocation-shadow drops them.
 * Execution-probe mail names may be empty. No FRED key. */
const FORWARDED_ENV_NAMES = [
  "R2_ACCOUNT_ID",
  "R2_BUCKET",
  "R2_ACCESS_KEY_ID",
  "R2_SECRET_ACCESS_KEY",
  "CORE_POSTGRES_URI",
  "CORE_SUPABASE_URL",
  "CORE_SUPABASE_SERVICE_KEY",
  "CLOUDFLARE_EMAIL_API_TOKEN",
  "CLOUDFLARE_ACCOUNT_ID",
  "NOTIFY_FROM",
  "DIGIQUANT_RUNNER_GIT_SHA",
  "DIGIQUANT_DIGIKEY_API_KEY",
  "OPENROUTER_API_KEY",
  "CHEAPERINFERENCE_API_KEY",
  "CHEAPERINFERENCE_API_BASE",
  "DIGI_OTEL_HEADERS",
] as const;

/** Container envVars whitelist. Omits RUNNER_AUTH_TOKEN.
 * House keys are present for the house-run allowlist; allocation-shadow drops them.
 * Execution-probe mail names may be empty. No FRED key.
 *
 * A name with no value is OMITTED, not forwarded as an empty string: the
 * container start config is merged over the image ENV, so an empty value
 * would override an image default that only applies when the name is absent
 * (DIGIQUANT_RUNNER_GIT_SHA). Only the mail names may arrive empty. */
export function dataPlaneEnv(env: Env): Record<string, string> {
  const forwarded: Record<string, string> = {};
  for (const name of FORWARDED_ENV_NAMES) {
    const value = env[name];
    if (typeof value === "string" && value !== "") {
      forwarded[name] = value;
      continue;
    }
    if ((MAIL_ENV_NAMES as readonly string[]).includes(name)) {
      forwarded[name] = "";
    }
  }
  return forwarded;
}
