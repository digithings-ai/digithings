"use client";

import { useEffect, useMemo, useState } from "react";
import {
  getTenantSuggestionPool,
  pickRandomEmbedSuggestions,
  pickStableEmbedSuggestions,
} from "@/lib/embed-suggestion-pools";
import type { EmbedTenantClientConfig } from "@/hooks/use-embed-tenant-config";

/**
 * Resolves embed suggestion chips: explicit URL overrides win; otherwise a random
 * subset of the tenant registry pool or slug defaults (3–4 items per mount).
 *
 * The first render uses a deterministic pick so SSR and hydration agree; the
 * random subset lands in an effect after mount.
 */
export function useEmbedSuggestions(
  urlSuggestions: string[] | undefined,
  tenantCfg: EmbedTenantClientConfig,
): string[] {
  const randomSuggestions = useMemo(() => {
    const pool = tenantCfg.suggestions ?? getTenantSuggestionPool(tenantCfg.slug) ?? [];
    if (!pool.length) return [];
    return pickStableEmbedSuggestions(pool);
  }, [tenantCfg.suggestions, tenantCfg.slug]);
  const [mountedSuggestions, setMountedSuggestions] = useState<string[] | null>(null);

  useEffect(() => {
    const pool = tenantCfg.suggestions ?? getTenantSuggestionPool(tenantCfg.slug) ?? [];
    if (!pool.length) return;
    // eslint-disable-next-line react-hooks/set-state-in-effect -- intentional one-shot mount sync: first render must match SSR (stable pick) to avoid a hydration mismatch; the reshuffled variety pick applies after mount.
    setMountedSuggestions(pickRandomEmbedSuggestions(pool));
  }, [tenantCfg.suggestions, tenantCfg.slug]);

  if (urlSuggestions?.length) return urlSuggestions;
  return mountedSuggestions ?? randomSuggestions;
}
