"use client";

import { useMemo } from "react";
import {
  getTenantSuggestionPool,
  pickRandomEmbedSuggestions,
} from "@/lib/embed-suggestion-pools";
import type { EmbedTenantClientConfig } from "@/hooks/use-embed-tenant-config";

/**
 * Resolves embed suggestion chips: explicit URL overrides win; otherwise a random
 * subset of the tenant registry pool or slug defaults (3–4 items per mount).
 */
export function useEmbedSuggestions(
  urlSuggestions: string[] | undefined,
  tenantCfg: EmbedTenantClientConfig,
): string[] {
  const randomSuggestions = useMemo(() => {
    const pool = tenantCfg.suggestions ?? getTenantSuggestionPool(tenantCfg.slug) ?? [];
    if (!pool.length) return [];
    return pickRandomEmbedSuggestions(pool);
  }, [tenantCfg.suggestions, tenantCfg.slug]);

  return urlSuggestions?.length ? urlSuggestions : randomSuggestions;
}
