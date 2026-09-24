"use client";

/**
 * Session prefs for full-app stock chrome (#3736). Same session toggles as
 * the embed — no sign-in required. MCP URLs never live here.
 *
 * WS4 Step 3: the hook takes a narrow structural config plus injectable deps
 * instead of the product `DigichatClientConfig`, so the module moves into the
 * package without importing app code. Behavior is unchanged — hosts pass the
 * same app functions and values.
 */

import { useCallback, useMemo, useRef, useState, type ReactNode } from "react";
import {
  DEFAULT_EMBED_CHAT_PREFS,
  EmbedChatPrefsProvider,
  catalogToolsFromClient,
  createDefaultEmbedChatPrefs,
  disabledCatalogIds,
  extraOffFromCatalog,
  type CatalogToolRow,
  type EmbedChatPrefs,
  type EmbedChatPrefsApi,
} from "@/components/stock/embed-chat-prefs";
import type { ComposerMenuKind } from "@/components/stock/embed-composer-menu";
import type { SessionMcpConfig } from "@/components/stock/embed-mcp-flow";
import type { ThinkingMode, ViewMode } from "@/lib/view-modes";

/** Narrow structural config: only the fields the prefs hook reads. */
export type StockChatPrefsConfig = {
  catalog: CatalogToolRow[];
  servers: CatalogToolRow[];
  defaultLanguage?: string;
  defaultModel?: string;
  availableModels: readonly string[];
  /** Host pre-computes models.allowPicker || features.modelPicker. */
  allowModelPicker?: boolean;
  view: ViewMode;
  thinking: ThinkingMode;
  tenantAllowsWeb: boolean;
  showByok: boolean;
  allowUserServers?: boolean;
  allowAddForm?: boolean;
};

/** Injectable product deps: pure app functions the package must not import. */
export type StockChatPrefsDeps = {
  defaultLanguageCode: string;
  detectLanguage?: () => string | undefined;
  resolveLanguage?: (code: string) => string | null | undefined;
  resolveWebSearch?: (tenantAllows: boolean, userPref: boolean) => boolean;
  mcpOps: {
    replace: (
      list: readonly SessionMcpConfig[],
      previousId: string,
      next: SessionMcpConfig,
    ) => SessionMcpConfig[];
    connected: (
      operator: readonly CatalogToolRow[],
      custom: readonly SessionMcpConfig[],
    ) => SessionMcpConfig[];
    headerValue: (
      configs: readonly SessionMcpConfig[],
      extraToolOn: (id: string) => boolean,
      allowSessionUrls: boolean,
    ) => string | undefined;
  };
  renderMenuPanes?: (args: {
    kind: ComposerMenuKind;
    models: readonly string[];
    providerSeed?: string;
    mcpSeed?: string;
    onClose: () => void;
  }) => ReactNode;
  onOpenSessions?: () => void;
};

const defaultResolveWebSearch = (tenantAllows: boolean, userPref: boolean) =>
  tenantAllows && userPref;

const defaultOpenSessions = () => {
  document.querySelector("[data-memory-thread-list]")?.scrollIntoView({
    block: "nearest",
  });
};

export function useStockChatPrefs({
  config,
  deps,
  sessionKey,
  hasSessions,
  newThread,
  redo,
}: {
  config: StockChatPrefsConfig;
  deps: StockChatPrefsDeps;
  sessionKey: string;
  hasSessions: boolean;
  newThread: () => void;
  redo: () => void;
}) {
  const catalogTools = useMemo(
    () =>
      catalogToolsFromClient({
        tools: { catalog: config.catalog },
        mcp: { servers: config.servers },
      }),
    [config.catalog, config.servers],
  );
  const [chatPrefs, setChatPrefs] = useState<EmbedChatPrefs>(() => ({
    ...DEFAULT_EMBED_CHAT_PREFS,
    language: (config.defaultLanguage || deps.detectLanguage?.()) ?? deps.defaultLanguageCode,
    model: config.defaultModel ?? config.availableModels[0] ?? "",
    extra: extraOffFromCatalog(catalogTools),
    view: config.view,
    thinking: config.thinking,
  }));
  const [composerMenu, setComposerMenu] = useState<null | ComposerMenuKind>(null);
  const [providerSeed, setProviderSeed] = useState<string | undefined>();
  const [mcpSeed, setMcpSeed] = useState<string | undefined>();
  const chatPrefsRef = useRef(chatPrefs);
  // eslint-disable-next-line react-hooks/refs -- send-time useLatest (#1339)
  chatPrefsRef.current = chatPrefs;

  const catalog = config.catalog;
  const tenantAllowsWeb = config.tenantAllowsWeb;
  const showByok = config.showByok;
  const showModels = config.allowModelPicker === true && config.availableModels.length > 0;

  const getLanguage = useCallback(() => chatPrefsRef.current.language, []);
  const getModel = useCallback(() => {
    const id = chatPrefsRef.current.model.trim();
    return id || undefined;
  }, []);
  const getDisabledTools = useCallback(
    () => disabledCatalogIds(chatPrefsRef.current).join(","),
    [],
  );
  const getEffort = useCallback(() => chatPrefsRef.current.effort, []);
  const getMcpSession = useCallback(
    () =>
      deps.mcpOps.headerValue(
        deps.mcpOps.connected(config.servers, chatPrefsRef.current.mcpCustom),
        (id) => chatPrefsRef.current.extra[id] !== false,
        config.allowUserServers === true,
      ),
    [config.servers, config.allowUserServers, deps.mcpOps],
  );
  const resolveWebSearch = deps.resolveWebSearch ?? defaultResolveWebSearch;
  const getEnableWebSearch = useCallback(
    () => resolveWebSearch(tenantAllowsWeb, chatPrefsRef.current.webSearch),
    [tenantAllowsWeb, resolveWebSearch],
  );

  const prefsApi = useMemo<EmbedChatPrefsApi>(
    () => ({
      prefs: chatPrefs,
      setWebSearch: (value) => setChatPrefs((p) => ({ ...p, webSearch: value })),
      setDigisearch: (value) => setChatPrefs((p) => ({ ...p, digisearch: value })),
      setVault: (value) => setChatPrefs((p) => ({ ...p, vault: value })),
      setExtraTool: (id, value) =>
        setChatPrefs((p) => ({ ...p, extra: { ...p.extra, [id]: value } })),
      extraToolOn: (id) => chatPrefs.extra[id] !== false,
      setMcpConfig: (config, previousId) =>
        setChatPrefs((p) => ({
          ...p,
          mcpCustom: deps.mcpOps.replace(p.mcpCustom, previousId ?? config.id, config),
        })),
      removeMcpConfig: (id) =>
        setChatPrefs((p) => ({
          ...p,
          mcpCustom: p.mcpCustom.filter((s) => s.id !== id),
        })),
      setLanguage: (code) => {
        const resolved = (deps.resolveLanguage ?? ((c) => c))(code) ?? deps.defaultLanguageCode;
        setChatPrefs((p) => ({ ...p, language: resolved }));
      },
      setView: (mode) => setChatPrefs((p) => ({ ...p, view: mode })),
      setThinking: (value) => setChatPrefs((p) => ({ ...p, thinking: value })),
      setModel: (id) => setChatPrefs((p) => ({ ...p, model: id })),
      setEffort: (effort) => setChatPrefs((p) => ({ ...p, effort })),
      reset: () =>
        setChatPrefs({
          ...createDefaultEmbedChatPrefs({ language: deps.defaultLanguageCode }),
          extra: extraOffFromCatalog(catalogTools),
          view: config.view,
          thinking: config.thinking,
        }),
      tenantAllowsWeb,
      showByok,
      showModels,
      hasDigisearch: catalog.some((e) => e.id === "digisearch"),
      hasVault: catalog.some((e) => e.id === "digivault"),
      hasSessions,
      allowUserMcp: config.allowUserServers === true,
      allowAddMcp: config.allowAddForm === true,
      catalogTools,
      mcpServers: config.servers,
      sessionKey,
      openSettings: () => {
        setComposerMenu("settings");
      },
      openTools: () => {
        setComposerMenu("tools");
      },
      openMcp: (seed?: string) => {
        setMcpSeed(seed);
        setComposerMenu("mcp");
      },
      openByok: (seed?: string) => {
        setProviderSeed(seed);
        setComposerMenu("provider");
      },
      openModels: () => {
        setComposerMenu("models");
      },
      openEffort: () => {
        setComposerMenu("effort");
      },
      openView: () => {
        setComposerMenu("view");
      },
      openThinking: () => {
        setComposerMenu("thinking");
      },
      openLanguage: () => {
        setComposerMenu("language");
      },
      openSessions: deps.onOpenSessions ?? defaultOpenSessions,
      newThread: () => {
        setChatPrefs({
          ...createDefaultEmbedChatPrefs({ language: deps.defaultLanguageCode }),
          extra: extraOffFromCatalog(catalogTools),
          view: config.view,
          thinking: config.thinking,
        });
        newThread();
      },
      compactThread: () => {
        setChatPrefs({
          ...createDefaultEmbedChatPrefs({ language: deps.defaultLanguageCode }),
          extra: extraOffFromCatalog(catalogTools),
          view: config.view,
          thinking: config.thinking,
        });
        newThread();
      },
      undo: () => {},
      redo,
    }),
    [
      chatPrefs,
      tenantAllowsWeb,
      showByok,
      showModels,
      catalog,
      catalogTools,
      sessionKey,
      hasSessions,
      newThread,
      redo,
      config.allowUserServers,
      config.allowAddForm,
      config.servers,
      config.view,
      config.thinking,
      deps.mcpOps,
      deps.resolveLanguage,
      deps.defaultLanguageCode,
      deps.onOpenSessions,
    ],
  );

  const panes = composerMenu ? (
    deps.renderMenuPanes?.({
      kind: composerMenu,
      models: config.availableModels,
      providerSeed,
      mcpSeed,
      onClose: () => {
        setComposerMenu(null);
        setProviderSeed(undefined);
        setMcpSeed(undefined);
      },
    }) ?? null
  ) : null;

  return {
    prefsApi,
    panes,
    getLanguage,
    getModel,
    getDisabledTools,
    getEnableWebSearch,
    getMcpSession,
    getEffort,
    setWebSearch: (on: boolean) => setChatPrefs((p) => ({ ...p, webSearch: on })),
  };
}

export function StockChatPrefsHost({
  value,
  children,
  panes,
}: {
  value: EmbedChatPrefsApi;
  children: ReactNode;
  panes: ReactNode;
}) {
  return (
    <EmbedChatPrefsProvider value={value}>
      {children}
      {panes}
    </EmbedChatPrefsProvider>
  );
}
