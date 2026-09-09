"use client";

/**
 * Session prefs for full-app stock chrome (#3736). Same session toggles as
 * the embed — no sign-in required. MCP URLs never live here.
 */

import { useCallback, useMemo, useRef, useState, type ReactNode } from "react";
import {
  DEFAULT_EMBED_CHAT_PREFS,
  EmbedChatPrefsProvider,
  catalogToolsFromClient,
  disabledCatalogIds,
  extraOffFromCatalog,
  type EmbedChatPrefs,
  type EmbedChatPrefsApi,
} from "@/components/stock/embed-chat-prefs";
import { EmbedComposerMenu, type ComposerMenuKind } from "@/components/stock/embed-composer-menu";
import { replaceMcpConfig, connectedMcpConfigs, mcpSessionOverlayHeaderValue } from "@/components/stock/embed-mcp-flow";
import type { DigichatClientConfig } from "@/lib/deploy-config";
import {
  DEFAULT_LANGUAGE_CODE,
  detectBrowserLanguageCode,
  tryResolveLanguageInput,
} from "@/lib/languages";
import { isWebSearchEnabled } from "@/lib/web-search-pref";

export function useStockChatPrefs({
  clientConfig,
  sessionKey,
  hasSessions,
  newThread,
  redo,
}: {
  clientConfig: DigichatClientConfig;
  sessionKey: string;
  hasSessions: boolean;
  newThread: () => void;
  redo: () => void;
}) {
  const catalogTools = useMemo(() => catalogToolsFromClient(clientConfig), [clientConfig]);
  const [chatPrefs, setChatPrefs] = useState<EmbedChatPrefs>(() => ({
    ...DEFAULT_EMBED_CHAT_PREFS,
    language: clientConfig.chrome.defaultLanguage || detectBrowserLanguageCode(),
    model: clientConfig.models.default ?? clientConfig.models.available[0] ?? "",
    extra: extraOffFromCatalog(catalogTools),
  }));
  const [composerMenu, setComposerMenu] = useState<null | ComposerMenuKind>(null);
  const [providerSeed, setProviderSeed] = useState<string | undefined>();
  const [mcpSeed, setMcpSeed] = useState<string | undefined>();
  const chatPrefsRef = useRef(chatPrefs);
  // eslint-disable-next-line react-hooks/refs -- send-time useLatest (#1339)
  chatPrefsRef.current = chatPrefs;

  const catalog = clientConfig.tools.catalog;
  const tenantAllowsWeb = clientConfig.gate.webSearch === true;
  const showByok = clientConfig.gate.showByok === true;
  const showModels =
    clientConfig.models.allowPicker === true || clientConfig.features.modelPicker === true;

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
      mcpSessionOverlayHeaderValue(
        connectedMcpConfigs(clientConfig.mcp.servers, chatPrefsRef.current.mcpCustom),
        (id) => chatPrefsRef.current.extra[id] !== false,
        clientConfig.mcp.allowUserServers === true,
      ),
    [clientConfig.mcp.servers, clientConfig.mcp.allowUserServers],
  );
  const getEnableWebSearch = useCallback(
    () =>
      isWebSearchEnabled({
        tenantAllows: tenantAllowsWeb,
        userPref: chatPrefsRef.current.webSearch,
      }),
    [tenantAllowsWeb],
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
          mcpCustom: replaceMcpConfig(p.mcpCustom, previousId ?? config.id, config),
        })),
      removeMcpConfig: (id) =>
        setChatPrefs((p) => ({
          ...p,
          mcpCustom: p.mcpCustom.filter((s) => s.id !== id),
        })),
      setLanguage: (code) => {
        const resolved = tryResolveLanguageInput(code) ?? DEFAULT_LANGUAGE_CODE;
        setChatPrefs((p) => ({ ...p, language: resolved }));
      },
      setThinking: (value) => setChatPrefs((p) => ({ ...p, thinking: value })),
      setModel: (id) => setChatPrefs((p) => ({ ...p, model: id })),
      setEffort: (effort) => setChatPrefs((p) => ({ ...p, effort })),
      reset: () =>
        setChatPrefs({
          ...DEFAULT_EMBED_CHAT_PREFS,
          language: DEFAULT_LANGUAGE_CODE,
          extra: extraOffFromCatalog(catalogTools),
        }),
      tenantAllowsWeb,
      showByok,
      showModels,
      hasDigisearch: catalog.length === 0 || catalog.some((e) => e.id === "digisearch"),
      hasVault: catalog.length === 0 || catalog.some((e) => e.id === "digivault"),
      hasSessions,
      allowUserMcp: clientConfig.mcp.allowUserServers === true,
      allowAddMcp: clientConfig.mcp.allowAddForm === true,
      catalogTools,
      mcpServers: clientConfig.mcp.servers,
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
      openLanguage: () => {
        setComposerMenu("language");
      },
      openSessions: () => {
        document.querySelector("[data-memory-thread-list]")?.scrollIntoView({
          block: "nearest",
        });
      },
      newThread: () => {
        setChatPrefs({
          ...DEFAULT_EMBED_CHAT_PREFS,
          language: DEFAULT_LANGUAGE_CODE,
          extra: extraOffFromCatalog(catalogTools),
        });
        newThread();
      },
      compactThread: () => {
        setChatPrefs({
          ...DEFAULT_EMBED_CHAT_PREFS,
          language: DEFAULT_LANGUAGE_CODE,
          extra: extraOffFromCatalog(catalogTools),
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
      clientConfig.mcp.allowUserServers,
      clientConfig.mcp.allowAddForm,
      clientConfig.mcp.servers,
    ],
  );

  const panes = composerMenu ? (
    <EmbedComposerMenu
      kind={composerMenu}
      models={clientConfig.models.available}
      onClose={() => {
        setComposerMenu(null);
        setProviderSeed(undefined);
        setMcpSeed(undefined);
      }}
      providerSeed={providerSeed}
      mcpSeed={mcpSeed}
    />
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
