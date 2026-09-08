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
import { EmbedSettingsPane } from "@/components/stock/embed-settings-pane";
import { EmbedMcpPane } from "@/components/stock/embed-mcp-pane";
import { EmbedModelsPane } from "@/components/stock/embed-models-pane";
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
  const [prefsOpen, setPrefsOpen] = useState(false);
  const [mcpOpen, setMcpOpen] = useState(false);
  const [modelsOpen, setModelsOpen] = useState(false);
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
      sessionKey,
      openSettings: () => {
        setMcpOpen(false);
        setModelsOpen(false);
        setPrefsOpen(true);
      },
      openMcp: () => {
        setPrefsOpen(false);
        setModelsOpen(false);
        setMcpOpen(true);
      },
      openByok: () => {
        setPrefsOpen(false);
        setMcpOpen(false);
        setModelsOpen(false);
      },
      openModels: () => {
        setPrefsOpen(false);
        setMcpOpen(false);
        setModelsOpen(true);
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
    ],
  );

  const panes = (
    <>
      {prefsOpen ? (
        <EmbedSettingsPane
          onClose={() => setPrefsOpen(false)}
          onByok={showByok ? () => setPrefsOpen(false) : undefined}
        />
      ) : null}
      {mcpOpen ? <EmbedMcpPane onClose={() => setMcpOpen(false)} /> : null}
      {modelsOpen ? (
        <EmbedModelsPane
          models={clientConfig.models.available}
          onClose={() => setModelsOpen(false)}
        />
      ) : null}
    </>
  );

  return {
    prefsApi,
    panes,
    getLanguage,
    getModel,
    getDisabledTools,
    getEnableWebSearch,
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
