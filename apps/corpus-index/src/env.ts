export type Env = {
  CORPUS_INDEX_KV: KVNamespace;
  CORPUS_INDEX_WORKFLOW: Workflow;
  AI: Ai;
  /** Read-only helpdesk token. Never log this value. */
  ZAMMAD_API_TOKEN?: string;
  /** Vectorize REST token. Index names come from KV, not from this binding. */
  CLOUDFLARE_API_TOKEN?: string;
  CLOUDFLARE_ACCOUNT_ID?: string;
  /** When unset, POST /run answers 404. */
  CRON_KICK_SECRET?: string;
  /** Bearer for POST /embed (digisearch query embedder). When unset, /embed answers 404. */
  EMBED_SECRET?: string;
  /** "1" fetches and masks but does not write vectors or the cursor. */
  DRY_RUN?: string;
};
