"use client";

/**
 * Session-only embed/popup prefs (#3733 / #3736). Reload and `/new` reset:
 * /digisearch and /digivault on, /websearch on, language English, view
 * balanced, thinking auto. Not localStorage.
 */

import { createContext, useContext, useEffect, type ReactNode } from "react";
import {
  readStoredDensity,
  resolveTraceDensity,
  writeStoredDensity,
  type TraceDensity,
} from "../trace-spacing";
import type { PaletteName, ResolvedTheme, ThemePreference } from "../../../theme/apply-theme";
import {
  normalizeViewPref,
  type ThinkingMode,
  type ViewMode,
  type SkinMcpServerConfig,
} from "./skin-types";

export type EmbedChatPrefs = {
  webSearch: boolean;
  digisearch: boolean;
  vault: boolean;
  /** Extra catalog / MCP server ids → enabled. Missing key means on. */
  extra: Record<string, boolean>;
  /** Session MCP JSON (user-added + operator overlays). Reload / /new clears. */
  mcpCustom: SkinMcpServerConfig[];
  language: string;
  /** Chain-of-thought view mode (reasoning + tool calls). */
  view: ViewMode;
  /** Reasoning-only override on top of `view`. */
  thinking: ThinkingMode;
  model: string;
  effort: string;
  /** Web-search engine id (auto/internal/exa/tavily/parallel/firecrawl/tinyfish). */
  searchEngine: string;
  /** The model/provider/MCP/context row under the composer. */
  toolbar: boolean;
  /** `always` keeps scrollbars in their reserved gutter; `auto` shows them on scroll. */
  scrollbars: "always" | "auto";
  /** Worked-chain rhythm. A stored user choice wins over the deployment default. */
  density: TraceDensity;
};

export const DEFAULT_EMBED_CHAT_PREFS: EmbedChatPrefs = {
  webSearch: true,
  digisearch: true,
  vault: true,
  extra: {},
  mcpCustom: [],
  // Session defaults mirror the app (`DEFAULT_LANGUAGE_CODE` / `DEFAULT_VIEW_MODE`
  // / `DEFAULT_THINKING_MODE`): English, balanced, auto. Literals keep the
  // package free of app imports (WS4); hosts inject their own via the factory.
  language: "en",
  view: "balanced",
  thinking: "auto",
  model: "",
  effort: "medium",
  searchEngine: "",
  toolbar: true,
  scrollbars: "always",
  density: "default",
};

/**
 * Session chrome seeded from a deployment. Density re-reads storage so a
 * user's palette choice survives `/new`; the rest return to the deployment.
 */
export function chromePrefsFromDeploy(
  input: {
    density?: string | null;
    effort?: string | null;
    searchEngine?: string | null;
    toolbar?: boolean | null;
    scrollbars?: "always" | "auto" | null;
  } = {},
  storage?: { getItem(key: string): string | null } | null,
): Pick<EmbedChatPrefs, "density" | "effort" | "searchEngine" | "toolbar" | "scrollbars"> {
  const effort = input.effort?.trim().toLowerCase();
  return {
    density: resolveTraceDensity(
      storage === undefined ? readStoredDensity() : readStoredDensity(storage),
      input.density,
    ),
    effort: effort === "low" || effort === "medium" || effort === "high" ? effort : "medium",
    searchEngine: input.searchEngine?.trim() ?? "",
    toolbar: input.toolbar !== false,
    scrollbars: input.scrollbars === "auto" ? "auto" : "always",
  };
}

/**
 * Apply a stored `dt-density` after hydration. The first render uses the
 * deployment density on both server and client, so `data-density` matches
 * and only a user with a stored choice re-renders once.
 */
export function useStoredDensityAfterMount(
  setPrefs: (update: (prev: EmbedChatPrefs) => EmbedChatPrefs) => void,
): void {
  useEffect(() => {
    const stored = readStoredDensity();
    if (!stored) return;
    // eslint-disable-next-line react-hooks/set-state-in-effect -- storage is client-only; reading it during render would mismatch the server HTML
    setPrefs((prev) => (prev.density === stored ? prev : { ...prev, density: stored }));
  }, [setPrefs]);
}

export function persistDensity(density: TraceDensity): void {
  writeStoredDensity(density);
}

/**
 * The package cannot import `@/lib/languages` / `@/lib/view-modes`, so hosts
 * pass their own defaults; called with no overrides it returns the app
 * defaults above, byte-for-byte.
 */
export function createDefaultEmbedChatPrefs(
  defaults?: { language?: string; view?: ViewMode; thinking?: ThinkingMode },
): EmbedChatPrefs {
  return {
    ...DEFAULT_EMBED_CHAT_PREFS,
    ...(defaults?.language !== undefined ? { language: defaults.language } : null),
    ...(defaults?.view !== undefined ? { view: normalizeViewPref(defaults.view) } : null),
    ...(defaults?.thinking !== undefined ? { thinking: defaults.thinking } : null),
  };
}

export type CatalogToolRow = {
  id: string;
  label?: string;
  default?: boolean;
  /** Individual tools under this entry (per-tool session toggles). */
  tools?: Array<{ id: string; label?: string }>;
};

export type EmbedChatPrefsApi = {
  prefs: EmbedChatPrefs;
  setWebSearch: (value: boolean) => void;
  setDigisearch: (value: boolean) => void;
  setVault: (value: boolean) => void;
  setExtraTool: (id: string, value: boolean) => void;
  extraToolOn: (id: string) => boolean;
  setMcpConfig: (config: SkinMcpServerConfig, previousId?: string) => void;
  removeMcpConfig: (id: string) => void;
  setLanguage: (code: string) => void;
  setView: (mode: ViewMode) => void;
  setThinking: (value: ThinkingMode) => void;
  setModel: (id: string) => void;
  setEffort: (effort: string) => void;
  setSearchEngine: (engine: string) => void;
  setToolbar: (visible: boolean) => void;
  setScrollbars: (mode: "always" | "auto") => void;
  setDensity: (density: TraceDensity) => void;
  reset: () => void;
  tenantAllowsWeb: boolean;
  showByok: boolean;
  /**
   * The backend that serves this chat, as a display label (an own-key
   * provider id, or the house backend id). The host owns the provider
   * vocabulary; absent means unknown, so the composer chip stays hidden
   * rather than naming a backend that may be wrong.
   */
  providerLabel?: string;
  showModels: boolean;
  /**
   * Model id used only to size the context meter. Not the session model:
   * an empty session model still sends no X-Digi-Model.
   */
  meterModel?: string;
  hasDigisearch: boolean;
  hasVault: boolean;
  hasSessions: boolean;
  /** A session artifact surface exists here. Gates the /artifacts row. */
  hasArtifacts: boolean;
  allowUserMcp: boolean;
  allowAddMcp: boolean;
  catalogTools: CatalogToolRow[];
  /** Operator MCP servers (ids/labels only — never URLs). */
  mcpServers: CatalogToolRow[];
  sessionKey: string;
  openSettings: () => void;
  /** Dedicated help panel: what the assistant can do and how to use it. */
  openHelp: () => void;
  openTools: () => void;
  openMcp: (seed?: string) => void;
  openByok: (seed?: string) => void;
  openModels: () => void;
  openEffort: () => void;
  openSearchEngine: () => void;
  openView: () => void;
  openDensity: () => void;
  /**
   * Hide `/theme` and ignore a typed one. No host sets this today: tenant
   * embeds offer `/theme` through `themeState` / `setTheme` (2.6.6). The full
   * app leaves this unset.
   */
  themeLocked?: boolean;
  /** Open the mode + palette picker. No-op when the host does not provide it. */
  openTheme?: () => void;
  /**
   * Host-owned theme (tenant embeds). When set, `/theme` and its picker read
   * this instead of the document-wide `dt-theme` / `dt-palette` keys, and a
   * pick goes through `setTheme` rather than `applyDocumentTheme`, so it is
   * not written to localStorage. `auto` drops the pick (back to the host's
   * default). The full app leaves both unset.
   */
  themeState?: { preference: ThemePreference; palette: PaletteName; resolved: ResolvedTheme };
  setTheme?: (preference: ThemePreference, palette: PaletteName) => void;
  openThinking: () => void;
  openLanguage: () => void;
  openSessions: () => void;
  openArtifacts: () => void;
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
      ...(t.tools?.length ? { tools: t.tools.map((x) => ({ ...x })) } : {}),
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
