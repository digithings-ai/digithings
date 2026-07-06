"use client";

import { useEffect, useState } from "react";
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
  const [suggestions, setSuggestions] = useState<string[]>(() => urlSuggestions ?? []);

  useEffect(() => {
    if (urlSuggestions?.length) {
      setSuggestions(urlSuggestions);
      return;
    }
    const pool = tenantCfg.suggestions ?? getTenantSuggestionPool(tenantCfg.slug) ?? [];
    if (!pool.length) return;
    setSuggestions((prev) => (prev.length ? prev : pickRandomEmbedSuggestions(pool)));
  }, [urlSuggestions, tenantCfg.suggestions, tenantCfg.slug]);

  return urlSuggestions?.length ? urlSuggestions : suggestions;
}
