/** digithings-cron Worker bindings. */
export interface Env {
  /** Fine-grained PAT / App token with Actions write on digithings + twelve-x. */
  GH_DISPATCH_TOKEN?: string;
  /** Optional; when set, POST /kick and GET /runs require Authorization: Bearer <secret>. */
  CRON_KICK_SECRET?: string;
  /** "1" logs intended GitHub POSTs without calling the API. Default "0". */
  DRY_RUN?: string;
  /** Service binding to the private digiquant-runner Worker. */
  RUNNER?: Fetcher;
  /** Service binding to the private twelvex-runner Worker. */
  TWELVEX_RUNNER?: Fetcher;
  /** Bearer for POST /v1/jobs on digiquant-runner. Required for kind "container". */
  RUNNER_AUTH_TOKEN?: string;
  /**
   * Bearer for POST /run/* on twelvex-runner. Kept separate from RUNNER_AUTH_TOKEN
   * so rotating it can never break digiquant-runner. Falls back to
   * RUNNER_AUTH_TOKEN when only one secret is deployed.
   */
  TWELVEX_RUNNER_AUTH?: string;
  /**
   * Comma-separated job ids that still workflow_dispatch GitHub Actions.
   * Default empty. Non-empty burns Actions minutes.
   */
  GITHUB_OVERRIDE_JOBS?: string;
  /**
   * Per-date remediation ledger for POST /backfill. Absent means the endpoint
   * answers 503 backfill_unconfigured rather than dispatching without a ledger,
   * because without it idempotence per date is not enforced.
   */
  BACKFILL_LEDGER?: DurableObjectNamespace;
  /**
   * "1" enables POST /backfill. Default "0". Off by default because a backfill
   * writes production snapshots; the endpoint must be turned on deliberately.
   */
  BACKFILL_ENABLED?: string;
  /**
   * Cron-tick claim ledger. Absent means the tick cannot detect a second
   * Cloudflare delivery and dispatches anyway (fail open), so a missing binding
   * costs duplicates, never a dropped clock.
   */
  START_COUNTER?: DurableObjectNamespace;
}

declare namespace Cloudflare {
  interface Env {
    GH_DISPATCH_TOKEN?: string;
    CRON_KICK_SECRET?: string;
    DRY_RUN?: string;
    RUNNER?: Fetcher;
    TWELVEX_RUNNER?: Fetcher;
    RUNNER_AUTH_TOKEN?: string;
    TWELVEX_RUNNER_AUTH?: string;
    GITHUB_OVERRIDE_JOBS?: string;
    BACKFILL_LEDGER?: DurableObjectNamespace;
    BACKFILL_ENABLED?: string;
    START_COUNTER?: DurableObjectNamespace;
  }
}
