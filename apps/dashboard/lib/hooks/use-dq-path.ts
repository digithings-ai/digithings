"use client";

import { apiGet } from "@/lib/api-client";
import { DQ_PATHS, type DqEnvelope, type DqPathKey } from "@/lib/dq-paths/registry";
import { useAsyncData } from "./use-async-data";

/**
 * Path-aware read: resolves a registry key to its DigiQuant API route and
 * returns the envelope (data + as_of + provenance). No parallel data layer —
 * a thin typed wrapper over `apiGet`.
 */
export function useDqPath<T>(key: DqPathKey, query?: Record<string, string>) {
  const def = DQ_PATHS[key];
  const state = useAsyncData<DqEnvelope<T> | null>(
    null,
    () => apiGet<DqEnvelope<T>>(def.apiRoute, query),
    [def.apiRoute, JSON.stringify(query ?? {})]
  );
  return { ...state, uiPath: def.uiPath, apiRoute: def.apiRoute };
}
