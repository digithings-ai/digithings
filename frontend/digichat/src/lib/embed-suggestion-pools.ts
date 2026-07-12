/** Default suggestion pools for embed tenants (full list; UI picks a random subset). */

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

const TENANT_SUGGESTION_POOLS: Record<string, readonly string[]> = {
  datatapstream: DATATAPSTREAM_SUGGESTION_POOL,
};

/** Full suggestion pool for a tenant slug, when the registry entry omits `suggestions`. */
export function getTenantSuggestionPool(slug: string): string[] | undefined {
  const pool = TENANT_SUGGESTION_POOLS[slug];
  return pool ? [...pool] : undefined;
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
