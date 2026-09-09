/**
 * Map deployment tool catalog ids → X-Digi-Force-Tool values the BFF may forward.
 * Server allowlist is source of truth; unknown / disallowed tools are dropped.
 */

import type { DigichatDeployment, ToolCatalogEntry } from "./schema";

/** Catalog id → upstream force-tool header value (when applicable). */
export const FORCE_TOOL_BY_CATALOG_ID: Readonly<Record<string, string>> = {
  digisearch: "digisearch",
  digivault: "digivault",
  search: "digisearch",
  vault: "digivault",
};

/** Slash / legacy force-tool aliases that map onto catalog ids. */
export const CATALOG_ID_BY_FORCE_TOOL: Readonly<Record<string, string>> = {
  digisearch: "digisearch",
  digivault: "digivault",
};

export function catalogAllowsForceTool(
  catalog: readonly ToolCatalogEntry[] | undefined,
  forceTool: string | null | undefined,
): boolean {
  const raw = forceTool?.trim();
  if (!raw) return false;
  // Legacy compat: empty catalog → allow digisearch/digivault only (pre-config installs).
  if (!catalog?.length) {
    return raw === "digisearch" || raw === "digivault";
  }
  const catalogId = CATALOG_ID_BY_FORCE_TOOL[raw] ?? raw;
  return catalog.some((e) => e.id === catalogId || FORCE_TOOL_BY_CATALOG_ID[e.id] === raw);
}

export function allowedForceTools(dep: DigichatDeployment | null | undefined): string[] {
  const catalog = dep?.tools?.catalog;
  if (!catalog?.length) return [];
  const out = new Set<string>();
  for (const e of catalog) {
    const mapped = FORCE_TOOL_BY_CATALOG_ID[e.id];
    if (mapped) out.add(mapped);
  }
  return [...out];
}

export function filterForceToolHeader(
  dep: DigichatDeployment | null | undefined,
  forceTool: string | null | undefined,
): string | undefined {
  const raw = forceTool?.trim();
  if (!raw) return undefined;
  if (!dep) return undefined;
  return catalogAllowsForceTool(dep.tools?.catalog, raw) ? raw : undefined;
}
