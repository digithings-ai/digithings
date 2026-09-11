"use client";

/**
 * Session-only embed/popup prefs (#3733 / #3736). Reload and `/new` reset:
 * /digisearch and /digivault on, /websearch on, language English, thinking on.
 * Not localStorage.
 */

import { createContext, useContext, type ReactNode } from "react";
import { DEFAULT_LANGUAGE_CODE } from "@/lib/languages";
import type { SessionMcpConfig } from "@/components/stock/embed-mcp-flow";

export type EmbedChatPrefs = {
  webSearch: boolean;
  digisearch: boolean;
  vault: boolean;
  /** Extra catalog / MCP server ids → enabled. Missing key means on. */
  extra: Record<string, boolean>;
  /** Session MCP JSON (user-added + operator overlays). Reload / /new clears. */
  mcpCustom: SessionMcpConfig[];
  language: string;
  thinking: boolean;
  model: string;
  effort: string;
};

export const DEFAULT_EMBED_CHAT_PREFS: EmbedChatPrefs = {
  webSearch: true,
  digisearch: true,
  vault: true,
  extra: {},
  mcpCustom: [],
  language: DEFAULT_LANGUAGE_CODE,
  thinking: true,
  model: "",
  effort: "medium",
};

export type CatalogToolRow = { id: string; label?: string; default?: boolean };

export type EmbedChatPrefsApi = {
  prefs: EmbedChatPrefs;
  setWebSearch: (value: boolean) => void;
  setDigisearch: (value: boolean) => void;
  setVault: (value: boolean) => void;
  setExtraTool: (id: string, value: boolean) => void;
  extraToolOn: (id: string) => boolean;
  setMcpConfig: (config: SessionMcpConfig, previousId?: string) => void;
  removeMcpConfig: (id: string) => void;
  setLanguage: (code: string) => void;
  setThinking: (value: boolean) => void;
  setModel: (id: string) => void;
  setEffort: (effort: string) => void;
  reset: () => void;
  tenantAllowsWeb: boolean;
  showByok: boolean;
  showModels: boolean;
  hasDigisearch: boolean;
  hasVault: boolean;
  hasSessions: boolean;
  allowUserMcp: boolean;
  allowAddMcp: boolean;
  catalogTools: CatalogToolRow[];
  /** Operator MCP servers (ids/labels only — never URLs). */
  mcpServers: CatalogToolRow[];
  sessionKey: string;
  openSettings: () => void;
  openTools: () => void;
  openMcp: (seed?: string) => void;
  openByok: (seed?: string) => void;
  openModels: () => void;
  openEffort: () => void;
  openLanguage: () => void;
  openSessions: () => void;
  newThread: () => void;
  compactThread: () => void | Promise<void>;
  undo: () => void;
  redo: () => void;
};

const EmbedChatPrefsContext = createContext<EmbedChatPrefsApi | null>(null);

export function EmbedChatPrefsProvider({
  value,
  children,
}: {
  value: EmbedChatPrefsApi;
  children: ReactNode;
}) {
  return (
    <EmbedChatPrefsContext.Provider value={value}>{children}</EmbedChatPrefsContext.Provider>
  );
}

export function useEmbedChatPrefsOptional(): EmbedChatPrefsApi | null {
  return useContext(EmbedChatPrefsContext);
}

export function useEmbedChatPrefs(): EmbedChatPrefsApi {
  const ctx = useContext(EmbedChatPrefsContext);
  if (!ctx) {
    throw new Error("useEmbedChatPrefs requires EmbedChatPrefsProvider");
  }
  return ctx;
}

/** Catalog ids to send as X-Digi-Disabled-Tools (web search uses its own header). */
export function disabledCatalogIds(prefs: EmbedChatPrefs): string[] {
  const out: string[] = [];
  if (!prefs.digisearch) out.push("digisearch");
  if (!prefs.vault) out.push("digivault");
  for (const [id, on] of Object.entries(prefs.extra)) {
    if (!on && id.trim()) out.push(id);
  }
  return out;
}

/** Catalog + operator MCP ids for slash/settings (never URLs). */
export function catalogToolsFromClient(cfg: {
  tools: { catalog: CatalogToolRow[] };
  mcp: { servers: CatalogToolRow[] };
}): CatalogToolRow[] {
  const seen = new Set<string>();
  const out: CatalogToolRow[] = [];
  for (const t of [...cfg.tools.catalog, ...cfg.mcp.servers]) {
    const id = t.id.trim();
    if (!id || seen.has(id)) continue;
    seen.add(id);
    out.push({
      id,
      ...(t.label ? { label: t.label } : {}),
      ...(typeof t.default === "boolean" ? { default: t.default } : {}),
    });
  }
  return out;
}

/** Extra catalog/MCP ids with `default: false` start off for this session. */
export function extraOffFromCatalog(tools: readonly CatalogToolRow[]): Record<string, boolean> {
  const extra: Record<string, boolean> = {};
  for (const t of tools) {
    if (t.id === "digisearch" || t.id === "digivault" || t.id === "web_search") continue;
    if (t.default === false) extra[t.id] = false;
  }
  return extra;
}
