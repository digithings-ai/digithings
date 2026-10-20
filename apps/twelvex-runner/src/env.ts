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
  /** Cheaper Inference key. Forwarded into the container as OPENAI_API_KEY. */
  CHEAPERINFERENCE_API_KEY?: string;
  /** Core project key. The FX research graph writes the shared core calendar. */
  CORE_SUPABASE_SERVICE_KEY?: string;
  /** Model endpoint the house path uses. */
  OPENAI_API_BASE?: string;
}

/**
 * Container envVars whitelist. Omits RUNNER_AUTH_TOKEN and GH_ISSUES_TOKEN.
 *
 * An optional variable that is not set is OMITTED, not forwarded as an empty
 * string. The twelve-x consumers read their own defaults with
 * `os.environ.get(NAME, DEFAULT)`, and that default applies only when the
 * variable is absent. Forwarding "" therefore turns a missing optional setting
 * into a hard failure (for example "supabase_url is required") instead of
 * letting the default apply.
 */
export function dataPlaneEnv(env: Env): Record<string, string> {
  const forwarded: Record<string, string> = {};
  if (env.PRIMEMARKET_SESSION_TOKEN) {
    forwarded.PRIMEMARKET_SESSION_TOKEN = env.PRIMEMARKET_SESSION_TOKEN;
  }
  if (env.TWELVEX_SUPABASE_SERVICE_KEY) {
    forwarded.TWELVEX_SUPABASE_SERVICE_KEY = env.TWELVEX_SUPABASE_SERVICE_KEY;
  }
  if (env.TWELVEX_SUPABASE_URL) {
    forwarded.TWELVEX_SUPABASE_URL = env.TWELVEX_SUPABASE_URL;
  }
  // The FX research session reads the model key and the core key by the names
  // the workflow uses, and the endpoint as a plain var.
  if (env.CHEAPERINFERENCE_API_KEY) {
    forwarded.OPENAI_API_KEY = env.CHEAPERINFERENCE_API_KEY;
  }
  if (env.CORE_SUPABASE_SERVICE_KEY) {
    forwarded.CORE_SUPABASE_SERVICE_KEY = env.CORE_SUPABASE_SERVICE_KEY;
  }
  if (env.OPENAI_API_BASE) {
    forwarded.OPENAI_API_BASE = env.OPENAI_API_BASE;
  }
  forwarded.DRY_RUN = env.DRY_RUN === "1" ? "1" : "0";
  return forwarded;
}
