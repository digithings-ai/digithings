import { LEGACY_GATED_TENANT_SLUG } from "@/lib/deploy-config/legacy-tenant-defaults";

/**
 * Suggestion pools (full list; the UI picks a random subset).
 *
 * A tenant's pool comes from its document (`chrome.suggestions`, registry
 * `suggestions`); code keeps only the house pool. The tenant pools below are
 * the legacy fallback for rows that do not carry `suggestions` yet.
 */

/** TODO(P-exit): legacy pool, read only when the tenant row has no suggestions. */
export const DATATAPSTREAM_SUGGESTION_POOL = [
  "What does the /api/config endpoint return?",
  "How do I authenticate API requests?",
  "How does the trial provisioning workflow work?",
  "What backup and restore options are available?",
  "How do I set up a Microsoft 365 connector?",
  "What workflow policies can I configure?",
  "How does the REST API handle pagination?",
  "What's the difference between public and premium API docs?",
  "How do I monitor job status and failures?",
  "What are the API rate limits?",
] as const;

/** digithings.ai — docs search, digivault, web search. One line per chip. */
export const DIGITHINGS_SUGGESTION_POOL = [
  "What is digigraph?",
  "Search the docs for NautilusTrader",
  "How do I run the stack locally?",
  "Summarize the digithings architecture",
  "What tools can you use?",
  "Search the vault for architecture notes",
] as const;

/** TODO(P-exit): legacy pool of the gated tenant (help corpus, vault, tickets). */
export const OCC_SUGGESTION_POOL = [
  "How do I file a support ticket?",
  "Search the help articles for onboarding",
  "Show my open Zammad tickets",
  "What is our data retention policy?",
  "Summarize the open Zammad tickets",
  "Check the status of my Zammad tickets",
] as const;

/** The house pool, by house slug. */
const HOUSE_SUGGESTION_POOLS: Record<string, readonly string[]> = {
  digithings: DIGITHINGS_SUGGESTION_POOL,
  "digithings-ai": DIGITHINGS_SUGGESTION_POOL,
};

/**
 * TODO(P-exit): legacy tenant pools, kept one release behind the fallback so
 * rows that do not carry `suggestions` yet render the same chips.
 */
const LEGACY_TENANT_SUGGESTION_POOLS: Record<string, readonly string[]> = {
  datatapstream: DATATAPSTREAM_SUGGESTION_POOL,
  [LEGACY_GATED_TENANT_SLUG]: OCC_SUGGESTION_POOL,
};

/**
 * Fallback pool for a slug, read only when the tenant document omits
 * `suggestions`: the house pool, else the legacy pool (one release).
 */
export function getTenantSuggestionPool(slug: string): string[] | undefined {
  const pool = HOUSE_SUGGESTION_POOLS[slug] ?? LEGACY_TENANT_SUGGESTION_POOLS[slug];
  return pool ? [...pool] : undefined;
}

/** First `count` items of `pool`, capped at 4 — deterministic pick for SSR/hydration. */
export function pickStableEmbedSuggestions(pool: readonly string[]): string[] {
  return [...pool].slice(0, Math.min(pool.length, 4));
}

/** Pick `min`–`max` unique items from `pool` (defaults 3–4). */
export function pickRandomEmbedSuggestions(
  pool: readonly string[],
  min = 3,
  max = 4,
): string[] {
  if (pool.length === 0) return [];
  const cap = Math.min(pool.length, max);
  const floor = Math.min(pool.length, min);
  const count =
    floor === cap ? floor : floor + Math.floor(Math.random() * (cap - floor + 1));
  const shuffled = [...pool];
  for (let i = shuffled.length - 1; i > 0; i--) {
    const j = Math.floor(Math.random() * (i + 1));
    [shuffled[i], shuffled[j]] = [shuffled[j], shuffled[i]];
  }
  return shuffled.slice(0, count);
}
