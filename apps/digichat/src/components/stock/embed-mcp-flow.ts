/**
 * Composer `/tools` + `/mcp` (#3736). MCP rows are tools with a status and a
 * session JSON the user can edit. Operator URLs never appear here.
 */

import {
  connectedToolIsOn as sharedConnectedToolIsOn,
  expandToolRows,
  HOUSE_BUILTIN_TOOL_IDS,
  HOUSE_SERVER_IDS as SHARED_HOUSE_SERVER_IDS,
} from "@digithings/ui/chat/tool-surface";

export const MCP_AUTH = ["none", "bearer", "oauth"] as const;
export type McpAuthKind = (typeof MCP_AUTH)[number];

export const MCP_ID_RE = /^[a-z0-9][a-z0-9_-]{0,63}$/;

export type McpSource = "operator" | "session";

export type SessionMcpConfig = {
  id: string;
  label: string;
  url: string;
  auth: McpAuthKind;
  token: string;
  extra: Record<string, string>;
  source: McpSource;
};

export type McpStatus = "active" | "disabled" | "needs_auth";

export type ConnectedToolRow = {
  id: string;
  slash: string;
  label: string;
  kind: "catalog" | "mcp";
  /** Individual tools under this row (per-tool session toggles). */
  tools?: ReadonlyArray<{ id: string; label?: string; group?: string }>;
  /**
   * The built-in tools a house service always offers, listed under it when the
   * deployment names none. They follow the service's switch; they are not
   * per-tool toggles, because the chat route only disables configured ids.
   */
  builtinTools?: ReadonlyArray<{ id: string }>;
};

/**
 * The digisearch tools that follow the digisearch switch: the set digigraph's
 * tool policy turns on and off with it (digigraph/src/digigraph/tool_policy.py).
 * Ids only — a row names a backend tool by its id and by nothing else. The
 * expansion lives in `@digithings/ui/chat/tool-surface` so the composer toolbar
 * counts exactly what `/tools` lists.
 */
export const DIGISEARCH_BUILTIN_TOOLS: ReadonlyArray<{ id: string }> = (
  HOUSE_BUILTIN_TOOL_IDS.digisearch ?? []
).map((id) => ({ id }));

/** The digivault tools that follow the digivault switch (same policy file). */
export const DIGIVAULT_BUILTIN_TOOLS: ReadonlyArray<{ id: string }> = (
  HOUSE_BUILTIN_TOOL_IDS.digivault ?? []
).map((id) => ({ id }));

type CatalogRef = {
  id: string;
  label?: string;
  tools?: ReadonlyArray<{ id: string; label?: string; group?: string }>;
};

export function emptyMcpConfig(): SessionMcpConfig {
  return {
    id: "",
    label: "",
    url: "",
    auth: "none",
    token: "",
    extra: {},
    source: "session",
  };
}

export function operatorMcpConfig(row: { id: string; label?: string }): SessionMcpConfig {
  const id = row.id.trim().toLowerCase();
  return {
    id,
    label: row.label?.trim() || id,
    url: "",
    auth: "none",
    token: "",
    extra: {},
    source: "operator",
  };
}

export function isMcpAuthKind(value: string): value is McpAuthKind {
  return (MCP_AUTH as readonly string[]).includes(value);
}

export function cycleMcpAuth(current: McpAuthKind, delta: number): McpAuthKind {
  const i = Math.max(0, MCP_AUTH.indexOf(current));
  const next = (i + delta + MCP_AUTH.length) % MCP_AUTH.length;
  return MCP_AUTH[next]!;
}

export function mergeMcpConfig(
  base: SessionMcpConfig,
  overlay?: SessionMcpConfig | null,
): SessionMcpConfig {
  if (!overlay) return base;
  return {
    ...base,
    label: overlay.label.trim() || base.label,
    url: base.source === "operator" ? "" : overlay.url,
    auth: overlay.auth,
    token: overlay.token,
    extra: { ...base.extra, ...overlay.extra },
    source: base.source,
  };
}

export function connectedMcpConfigs(
  operator: readonly CatalogRef[],
  custom: readonly SessionMcpConfig[],
): SessionMcpConfig[] {
  const overlays = new Map(custom.map((s) => [s.id, s]));
  const seen = new Set<string>();
  const out: SessionMcpConfig[] = [];
  for (const s of operator) {
    const id = s.id.trim().toLowerCase();
    if (!id || seen.has(id)) continue;
    seen.add(id);
    out.push(mergeMcpConfig(operatorMcpConfig(s), overlays.get(id)));
  }
  for (const s of custom) {
    const id = s.id.trim().toLowerCase();
    if (!id || seen.has(id)) continue;
    seen.add(id);
    out.push({ ...s, id, source: "session" });
  }
  return out;
}

export function mcpStatus(cfg: SessionMcpConfig, enabled: boolean): McpStatus {
  if (!enabled) return "disabled";
  if (cfg.auth !== "none" && !cfg.token.trim()) return "needs_auth";
  return "active";
}

export function mcpStatusLabel(status: McpStatus): string {
  if (status === "active") return "Active";
  if (status === "disabled") return "Disabled";
  return "Needs auth";
}

/** Public JSON — operator URL omitted; token masked. */
export function mcpConfigRecord(cfg: SessionMcpConfig): Record<string, string> {
  const rec: Record<string, string> = {
    id: cfg.id,
    label: cfg.label,
    auth: cfg.auth,
  };
  if (cfg.source === "session") rec.url = cfg.url;
  if (cfg.auth !== "none") rec.token = cfg.token.trim() ? "••••" : "";
  for (const [k, v] of Object.entries(cfg.extra)) {
    if (k.trim()) rec[k] = v;
  }
  return rec;
}

export function mcpConfigJson(cfg: SessionMcpConfig): string {
  return `${JSON.stringify(mcpConfigRecord(cfg), null, 2)}\n`;
}

export function parseMcpSeed(raw: string): "new" | string | undefined {
  const q = raw.trim().toLowerCase();
  if (!q) return undefined;
  if (q === "new" || q === "add") return "new";
  if (MCP_ID_RE.test(q)) return q;
  return undefined;
}

export function upsertMcpConfig(
  list: readonly SessionMcpConfig[],
  next: SessionMcpConfig,
): SessionMcpConfig[] {
  const id = next.id.trim().toLowerCase();
  if (!MCP_ID_RE.test(id)) return [...list];
  const row: SessionMcpConfig = { ...next, id };
  const i = list.findIndex((s) => s.id === id);
  if (i < 0) return [...list, row];
  return list.map((s, idx) => (idx === i ? row : s));
}

/** Persist a draft, dropping the previous session id when the slug changes. */
export function replaceMcpConfig(
  list: readonly SessionMcpConfig[],
  previousId: string,
  next: SessionMcpConfig,
): SessionMcpConfig[] {
  const prev = previousId.trim().toLowerCase();
  const id = next.id.trim().toLowerCase();
  const without = prev && prev !== id ? list.filter((s) => s.id !== prev) : list;
  return upsertMcpConfig(without, next);
}

export function catalogSlashId(id: string): string {
  return id === "web_search" ? "websearch" : id;
}

/**
 * The house services whose backend id is also their only public name. A
 * deployment used to label them "Search"/"Vault"; a tenant document (or an
 * OCC row) that still does must not leak that vocabulary into `/tools`, `/mcp`
 * or the menu summaries. Individual tools already render raw backend ids
 * (digivault_get_note), so the group cannot use a different vocabulary.
 */
export const HOUSE_SERVER_IDS: ReadonlySet<string> = SHARED_HOUSE_SERVER_IDS;

/**
 * Whether a row is on. The rule lives in `@digithings/ui/chat/tool-surface` and the
 * composer toolbar counts with the same one.
 */
export const connectedToolIsOn = sharedConnectedToolIsOn;

/**
 * The rendered name of a server row: the backend id for the house services,
 * otherwise the deployment label with the id as fallback. Never a title-cased
 * or otherwise derived pretty name.
 */
export function serverRowLabel(id: string, _label?: string): string {
  // Raw backend id, always. A deployment label is how an operator describes a
  // server to themselves; the row must name what the backend calls it, so the
  // chat and the tool trace never disagree.
  return id.trim();
}

export function connectedTools(input: {  hasDigisearch: boolean;
  hasVault: boolean;
  tenantAllowsWeb: boolean;
  catalogTools: readonly CatalogRef[];
  mcpServers: readonly CatalogRef[];
  mcpCustom: readonly SessionMcpConfig[];
}): ConnectedToolRow[] {
  const mcp = connectedMcpConfigs(input.mcpServers, input.mcpCustom);
  const mcpIds = new Set(mcp.map((s) => s.id));
  /**
   * Labels are raw backend ids everywhere: `serverRowLabel` returns the id,
   * and the web search row uses the backend's own `web_search`. The sub-tool
   * list comes from the one expansion the toolbar counts with, so a house row
   * the deployment did not break down shows the built-in pair here and is
   * counted as that pair there.
   */
  const subsOf = (id: string) => {
    const declared =
      input.catalogTools.find((t) => t.id === id)?.tools ??
      input.mcpServers.find((t) => t.id === id)?.tools;
    const row = expandToolRows([{ id, tools: declared }])[0]!;
    if (row.builtin) return { builtinTools: row.tools.map((toolId) => ({ id: toolId })) };
    return row.tools.length ? { tools: declared } : {};
  };
  const rows: ConnectedToolRow[] = [];
  if (input.hasDigisearch) {
    rows.push({
      id: "digisearch",
      slash: "digisearch",
      label: serverRowLabel("digisearch"),
      kind: "catalog",
      ...subsOf("digisearch"),
    });
  }
  if (input.hasVault) {
    rows.push({
      id: "digivault",
      slash: "digivault",
      label: serverRowLabel("digivault"),
      kind: "catalog",
      ...subsOf("digivault"),
    });
  }
  if (input.tenantAllowsWeb) {
    rows.push({
      id: "websearch",
      slash: "websearch",
      label: "web_search",
      kind: "catalog",
    });
  }
  for (const t of input.catalogTools) {
    const id = t.id.trim();
    if (
      !id ||
      id === "digisearch" ||
      id === "digivault" ||
      id === "web_search" ||
      mcpIds.has(id)
    ) {
      continue;
    }
    rows.push({
      id,
      slash: catalogSlashId(id),
      label: id,
      kind: "catalog",
      ...subsOf(id),
    });
  }
  // One row per backend id. A service row is pushed above when its capability
  // is on, and the same id also arrives in `mcp.servers`; without this guard
  // the menu lists digisearch and digivault twice.
  const seen = new Set(rows.map((r) => r.id));
  for (const s of mcp) {
    if (seen.has(s.id)) continue;
    seen.add(s.id);
    rows.push({
      id: s.id,
      slash: s.id,
      label: serverRowLabel(s.id, s.label),
      kind: "mcp",
      ...subsOf(s.id),
    });
  }
  return rows;
}

export function toolsMenuSummary(
  rows: readonly ConnectedToolRow[],
  isOn: (id: string) => boolean,
): string {
  if (!rows.length) return "None";
  const on = rows.filter((r) => isOn(r.id));
  if (!on.length) return "Off";
  if (on.length === rows.length) return "All on";
  if (on.length === 1) return on[0]!.label;
  return `${on.length} on`;
}

export function mcpMenuSummaryFromConfigs(
  servers: readonly SessionMcpConfig[],
  extraToolOn: (id: string) => boolean,
): string {
  if (!servers.length) return "None";
  const on = servers.filter((s) => extraToolOn(s.id));
  if (!on.length) return "Off";
  if (on.length === 1) return serverRowLabel(on[0]!.id, on[0]!.label);
  return `${on.length} on`;
}

export type McpSessionOverlayItem = {
  id: string;
  url?: string;
  auth: McpAuthKind;
  token?: string;
};

/** Client header for X-Digi-Mcp-Session — operator URLs never included. */
export function mcpSessionOverlayItems(
  configs: readonly SessionMcpConfig[],
  extraToolOn: (id: string) => boolean,
  allowSessionUrls: boolean,
): McpSessionOverlayItem[] {
  const out: McpSessionOverlayItem[] = [];
  for (const c of configs) {
    if (!extraToolOn(c.id)) continue;
    const token = c.token.trim();
    if (c.source === "operator") {
      if (!token) continue;
      out.push({ id: c.id, auth: c.auth, token });
      continue;
    }
    if (!allowSessionUrls) continue;
    const url = c.url.trim();
    if (!url) continue;
    out.push({
      id: c.id,
      url,
      auth: c.auth,
      ...(token ? { token } : {}),
    });
  }
  return out;
}

export function mcpSessionOverlayHeaderValue(
  configs: readonly SessionMcpConfig[],
  extraToolOn: (id: string) => boolean,
  allowSessionUrls: boolean,
): string | undefined {
  const items = mcpSessionOverlayItems(configs, extraToolOn, allowSessionUrls);
  if (!items.length) return undefined;
  const json = JSON.stringify(items);
  if (json.length > 8_192) return undefined;
  return json;
}
