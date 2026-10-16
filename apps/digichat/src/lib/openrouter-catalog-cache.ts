import { BoundedTTLMap } from "@/lib/bounded-map";
import type { OpenRouterCatalogBuckets } from "@/lib/openrouter-catalog";

/** In-process memo for the public OpenRouter model catalog (#2408). */
const CACHE_TTL_MS = 10 * 60_000; // 10 minutes
const cache = new BoundedTTLMap<string, OpenRouterCatalogBuckets>(4, CACHE_TTL_MS);

export function readOpenRouterCatalogCache(): OpenRouterCatalogBuckets | undefined {
  return cache.get("openrouter");
}

export function writeOpenRouterCatalogCache(buckets: OpenRouterCatalogBuckets): void {
  cache.set("openrouter", buckets);
}

/** Test hook — clears the module-level catalog cache. */
export function resetOpenRouterCatalogCache(): void {
  cache.clear();
}
