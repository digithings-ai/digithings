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
  digivault_search_notes: "digivault",
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
  return catalogAllowsForceTool(dep?.tools?.catalog, raw) ? raw : undefined;
}

/** Catalog ids a user may disable for the session (#3733). */
export const DISABLEABLE_CATALOG_IDS = ["digisearch", "digivault"] as const;

export type DisableableCatalogId = (typeof DISABLEABLE_CATALOG_IDS)[number];

/** Upstream tool names dropped when a catalog id is disabled. */
export const DISABLED_TOOLS_BY_CATALOG_ID: Readonly<
  Record<DisableableCatalogId, readonly string[]>
> = {
  digisearch: ["digisearch", "digisearch_fetch_all"],
  digivault: ["digivault", "digivault_search_notes", "digivault_get_note"],
};

const DISABLE_ALIASES: Readonly<Record<string, string>> = {
  digisearch: "digisearch",
  search: "digisearch",
  digivault: "digivault",
  vault: "digivault",
  docs: "digivault",
};

export function catalogAllowsDisableId(
  catalog: readonly ToolCatalogEntry[] | undefined,
  catalogId: string,
): boolean {
  const mapped = DISABLE_ALIASES[catalogId.trim().toLowerCase()];
  if (!mapped) return false;
  if (!catalog?.length) {
    return mapped === "digisearch" || mapped === "digivault";
  }
  return catalog.some((e) => e.id === mapped || FORCE_TOOL_BY_CATALOG_ID[e.id] === mapped);
}

/**
 * Fail-closed parse of X-Digi-Disabled-Tools. Unknown tokens dropped.
 * Empty catalog → allow digisearch/digivault only (same as force-tool).
 */
export function filterDisabledToolsHeader(
  dep: DigichatDeployment | null | undefined,
  raw: string | null | undefined,
): string[] {
  if (!raw?.trim()) return [];
  const catalog = dep?.tools?.catalog;
  const out: string[] = [];
  const seen = new Set<string>();
  for (const token of raw.split(",")) {
    const mapped = DISABLE_ALIASES[token.trim().toLowerCase()];
    if (!mapped || seen.has(mapped)) continue;
    if (!catalogAllowsDisableId(catalog, mapped)) continue;
    seen.add(mapped);
    out.push(mapped);
  }
  return out;
}

export function expandDisabledCatalogIds(ids: readonly string[]): string[] {
  const names = new Set<string>();
  for (const id of ids) {
    const mapped = DISABLED_TOOLS_BY_CATALOG_ID[id as DisableableCatalogId];
    if (mapped) {
      for (const n of mapped) names.add(n);
    }
  }
  return [...names];
}

/** Force-with-query wins: do not disable the catalog id being forced this send. */
export function omitForcedCatalogIds(
  disabled: readonly string[],
  forceTool: string | null | undefined,
): string[] {
  const raw = forceTool?.trim();
  if (!raw) return [...disabled];
  const catalogId = CATALOG_ID_BY_FORCE_TOOL[raw] ?? FORCE_TOOL_BY_CATALOG_ID[raw] ?? raw;
  const skip =
    catalogId === "digisearch" || catalogId === "search"
      ? "digisearch"
      : catalogId === "digivault" ||
          catalogId === "vault" ||
          catalogId === "docs" ||
          catalogId === "digivault_search_notes"
        ? "digivault"
        : undefined;
  if (!skip) return [...disabled];
  return disabled.filter((id) => id !== skip);
}
