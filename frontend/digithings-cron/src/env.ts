/** digithings-cron Worker bindings. */
export interface Env {
  /** Fine-grained PAT / App token with Actions write on digithings + twelve-x. */
  GH_DISPATCH_TOKEN?: string;
  /** Optional; when set, POST /kick requires Authorization: Bearer <secret>. */
  CRON_KICK_SECRET?: string;
  /** "1" logs intended GitHub POSTs without calling the API. Default "0". */
  DRY_RUN?: string;
}

declare namespace Cloudflare {
  interface Env {
    GH_DISPATCH_TOKEN?: string;
    CRON_KICK_SECRET?: string;
    DRY_RUN?: string;
  }
}
