/**
 * The tool set, expanded once (#tool-contract).
 *
 * The composer toolbar prints a tool count and `/tools` prints the rows behind
 * it. They used to compute that set separately — the toolbar over
 * `prefs.mcpServers` with its own formula, the menu over `allowedTools` plus a
 * built-in substitution — and disagreed on the same deployment. This module is
 * the only expansion: raw backend ids in, one row per server with its
 * effective tools out, plus the count derived from the same rows.
 *
 * Every id here is a backend id. Nothing in this file humanises a name.
 */

/** A row that can carry per-tool entries, as the host projects it. */
export type ToolSurfaceRowInput = {
  id: string;
  /** Individual tools under this row, raw backend ids. */
  tools?: ReadonlyArray<{ id: string }>;
};

export type ToolSurfaceRow = {
  id: string;
  /** Effective tool ids under this row. Raw backend ids, never labels. */
  tools: readonly string[];
  /**
   * True when `tools` is the house built-in set rather than a list the
   * deployment named. A deployment that names no tools for a house service
   * leaves the row governed by that service's switch, so its two built-ins
   * are what the switch actually turns on and off
   * (digigraph/src/digigraph/tool_policy.py).
   */
  builtin: boolean;
};

/**
 * The tools a house switch carries, by backend id. Kept in step with
 * digigraph's `_DISABLE_TOOL_ALIASES` (digigraph/src/digigraph/tool_policy.py):
 * disabling `digisearch` strips both of its pair, disabling `digivault` strips
 * both of its pair.
 */
export const HOUSE_BUILTIN_TOOL_IDS: Readonly<Record<string, readonly string[]>> = {
  digisearch: ["digisearch", "digisearch_fetch_all"],
  digivault: ["digivault_search_notes", "digivault_get_note"],
};

/** The house service ids that carry a built-in pair. */
export const HOUSE_SERVER_IDS: ReadonlySet<string> = new Set(Object.keys(HOUSE_BUILTIN_TOOL_IDS));

/**
 * One row per server, with the tools a deployment actually gets under it:
 * the declared `tools` when the row names any, else the house built-in pair
 * for that service id, else nothing.
 */
export function expandToolRows(
  rows: readonly ToolSurfaceRowInput[],
): ToolSurfaceRow[] {
  return rows.map((row) => {
    const declared = (row.tools ?? []).map((tool) => tool.id.trim()).filter(Boolean);
    if (declared.length) return { id: row.id.trim(), tools: declared, builtin: false };
    const builtin = HOUSE_BUILTIN_TOOL_IDS[row.id.trim()] ?? [];
    return {
      id: row.id.trim(),
      tools: builtin,
      builtin: builtin.length > 0,
    };
  });
}

export type ToolSurfaceCount = {
  servers: number;
  tools: number;
};

/**
 * The count the toolbar prints, derived from the rows `/tools` renders.
 *
 * A row counts once while it is on and carries at least one tool; a row with
 * no tools is one tool, because a server nobody has broken down is still one
 * thing the assistant can call.
 */
export function countToolSurface(
  rows: readonly ToolSurfaceRowInput[],
  input: {
    isOn: (rowId: string) => boolean;
    isToolOn: (toolId: string) => boolean;
  },
): ToolSurfaceCount {
  const counts: ToolSurfaceCount = { servers: 0, tools: 0 };
  for (const row of expandToolRows(rows)) {
    if (!input.isOn(row.id)) continue;
    const enabled = row.tools.length
      ? row.tools.filter((id) => input.isToolOn(id)).length
      : 1;
    if (enabled === 0) continue;
    counts.servers += 1;
    counts.tools += enabled;
  }
  return counts;
}

/**
 * Whether a row is on. Kept here, not in the host, so the toolbar and the menu
 * answer with the same rule: a house service follows its own switch, web
 * search follows the tenant's, everything else falls back to the session
 * toggle.
 */
export function connectedToolIsOn(
  id: string,
  input: {
    digisearch: boolean;
    vault: boolean;
    webSearch: boolean;
    extraToolOn: (id: string) => boolean;
  },
): boolean {
  if (id === "digisearch") return input.digisearch;
  if (id === "digivault") return input.vault;
  if (id === "websearch" || id === "web_search") return input.webSearch;
  return input.extraToolOn(id);
}
