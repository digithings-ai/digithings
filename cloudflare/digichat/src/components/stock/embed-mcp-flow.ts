/**
 * Composer `/tools` + `/mcp` (#3736). MCP rows are tools with a status and a
 * session JSON the user can edit. Operator URLs never appear here.
 */

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
};

type CatalogRef = { id: string; label?: string };

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

export function connectedTools(input: {
  hasDigisearch: boolean;
  hasVault: boolean;
  tenantAllowsWeb: boolean;
  catalogTools: readonly CatalogRef[];
  mcpServers: readonly CatalogRef[];
  mcpCustom: readonly SessionMcpConfig[];
}): ConnectedToolRow[] {
  const mcp = connectedMcpConfigs(input.mcpServers, input.mcpCustom);
  const mcpIds = new Set(mcp.map((s) => s.id));
  const labelOf = (id: string, fallback: string) =>
    input.catalogTools.find((t) => t.id === id)?.label?.trim() || fallback;
  const rows: ConnectedToolRow[] = [];
  if (input.hasDigisearch) {
    rows.push({
      id: "digisearch",
      slash: "digisearch",
      label: labelOf("digisearch", "Search"),
      kind: "catalog",
    });
  }
  if (input.hasVault) {
    rows.push({
      id: "digivault",
      slash: "digivault",
      label: labelOf("digivault", "Vault"),
      kind: "catalog",
    });
  }
  if (input.tenantAllowsWeb) {
    rows.push({
      id: "websearch",
      slash: "websearch",
      label: labelOf("web_search", "Web search"),
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
      label: t.label?.trim() || id,
      kind: "catalog",
    });
  }
  for (const s of mcp) {
    rows.push({
      id: s.id,
      slash: s.id,
      label: s.label || s.id,
      kind: "mcp",
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
  if (on.length === 1) return on[0]!.label.trim() || on[0]!.id;
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
