import { LEGACY_TENANT_SUGGESTION_POOLS } from "./legacy-suggestion-pools";

/**
 * Suggestion pools (full list; the UI picks a random subset).
 *
 * A tenant's pool comes from its document (`chrome.suggestions`, registry
 * `suggestions`); code keeps only the house pool. Legacy tenant pools, the
 * fallback for rows that do not carry `suggestions` yet, live in
 * `./legacy-suggestion-pools` (deployment data; the public repo ships an
 * empty stand-in).
 */

/** digithings.ai — docs search, digivault, web search. One line per chip. */
export const DIGITHINGS_SUGGESTION_POOL = [
  "What is digigraph?",
  "Search the docs for NautilusTrader",
  "How do I run the stack locally?",
  "Summarize the digithings architecture",
  "What tools can you use?",
  "Search the vault for architecture notes",
] as const;

/** The house pool, by house slug. */
const HOUSE_SUGGESTION_POOLS: Record<string, readonly string[]> = {
  digithings: DIGITHINGS_SUGGESTION_POOL,
  "digithings-ai": DIGITHINGS_SUGGESTION_POOL,
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
export function pickRandomEmbedSuggestions(pool: readonly string[], min = 3, max = 4): string[] {
  if (pool.length === 0) return [];
  const cap = Math.min(pool.length, max);
  const floor = Math.min(pool.length, min);
  const count = floor === cap ? floor : floor + Math.floor(Math.random() * (cap - floor + 1));
  const shuffled = [...pool];
  for (let i = shuffled.length - 1; i > 0; i--) {
    const j = Math.floor(Math.random() * (i + 1));
    [shuffled[i], shuffled[j]] = [shuffled[j], shuffled[i]];
  }
  return shuffled.slice(0, count);
}
