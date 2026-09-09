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
  mcpIds?: readonly string[],
): boolean {
  const raw = forceTool?.trim();
  if (!raw) return false;
  // Legacy compat: empty catalog → allow digisearch/digivault only (pre-config installs).
  if (!catalog?.length && !mcpIds?.length) {
    return raw === "digisearch" || raw === "digivault";
  }
  const catalogId = CATALOG_ID_BY_FORCE_TOOL[raw] ?? raw;
  if (catalog?.some((e) => e.id === catalogId || FORCE_TOOL_BY_CATALOG_ID[e.id] === raw)) {
    return true;
  }
  return (mcpIds ?? []).includes(catalogId);
}

export function allowedForceTools(dep: DigichatDeployment | null | undefined): string[] {
  const catalog = dep?.tools?.catalog;
  const out = new Set<string>();
  if (!catalog?.length) {
    out.add("digisearch");
    out.add("digivault");
  } else {
    for (const e of catalog) {
      const mapped = FORCE_TOOL_BY_CATALOG_ID[e.id] ?? (e.id !== "web_search" ? e.id : undefined);
      if (mapped) out.add(mapped);
    }
  }
  for (const s of dep?.mcp?.servers ?? []) {
    if (s.id.trim()) out.add(s.id.trim());
  }
  return [...out];
}

export function filterForceToolHeader(
  dep: DigichatDeployment | null | undefined,
  forceTool: string | null | undefined,
): string | undefined {
  const raw = forceTool?.trim();
  if (!raw) return undefined;
  const mcpIds = (dep?.mcp?.servers ?? []).map((s) => s.id);
  return catalogAllowsForceTool(dep?.tools?.catalog, raw, mcpIds) ? raw : undefined;
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

function extraDisableableIds(dep: DigichatDeployment | null | undefined): Set<string> {
  const out = new Set<string>();
  for (const e of dep?.tools?.catalog ?? []) {
    const id = e.id.trim().toLowerCase();
    if (id && id !== "web_search") out.add(id);
  }
  for (const s of dep?.mcp?.servers ?? []) {
    const id = s.id.trim().toLowerCase();
    if (id) out.add(id);
  }
  return out;
}

export function catalogAllowsDisableId(
  catalog: readonly ToolCatalogEntry[] | undefined,
  catalogId: string,
  extraIds?: ReadonlySet<string>,
): boolean {
  const mapped = DISABLE_ALIASES[catalogId.trim().toLowerCase()] ?? catalogId.trim().toLowerCase();
  if (!mapped || mapped === "web_search") return false;
  if (DISABLEABLE_CATALOG_IDS.includes(mapped as DisableableCatalogId)) {
    if (!catalog?.length) {
      return mapped === "digisearch" || mapped === "digivault";
    }
    return catalog.some((e) => e.id === mapped || FORCE_TOOL_BY_CATALOG_ID[e.id] === mapped);
  }
  if (extraIds?.has(mapped)) return true;
  if (catalog?.some((e) => e.id === mapped)) return true;
  return false;
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
  const extra = extraDisableableIds(dep);
  const out: string[] = [];
  const seen = new Set<string>();
  for (const token of raw.split(",")) {
    const rawId = token.trim().toLowerCase();
    const mapped = DISABLE_ALIASES[rawId] ?? rawId;
    if (!mapped || seen.has(mapped)) continue;
    if (!catalogAllowsDisableId(catalog, mapped, extra)) continue;
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
        : catalogId;
  if (!skip) return [...disabled];
  return disabled.filter((id) => id !== skip);
}
