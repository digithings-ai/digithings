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
  /** Bearer for POST /v1/jobs on digiquant-runner. Required for kind "container". */
  RUNNER_AUTH_TOKEN?: string;
  /**
   * Comma-separated job ids that still workflow_dispatch GitHub Actions.
   * Default empty. Non-empty burns Actions minutes.
   */
  GITHUB_OVERRIDE_JOBS?: string;
}

declare namespace Cloudflare {
  interface Env {
    GH_DISPATCH_TOKEN?: string;
    CRON_KICK_SECRET?: string;
    DRY_RUN?: string;
    RUNNER?: Fetcher;
    RUNNER_AUTH_TOKEN?: string;
    GITHUB_OVERRIDE_JOBS?: string;
  }
}
