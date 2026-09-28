"use client";

/**
 * Anonymous / memory app shell: stock Thread → POST /api/chat.
 * persistence=memory: useRemoteThreadListRuntime + SessionMemoryThreadListAdapter
 * and ThreadListPrimitive sidebar (inside the runtime provider).
 */

import { useMemo, useRef, useState } from "react";
import { useChat } from "@ai-sdk/react";
import type { UIMessage } from "ai";
import { AssistantChatTransport, useAISDKRuntime } from "@assistant-ui/ai-sdk";
import { useRemoteThreadListRuntime } from "@assistant-ui/react";
import {
  ProductStockShell,
  buildProductRuntimeAdapters,
} from "@/components/stock/product-shell";
import { MemoryThreadListSidebar } from "@/components/stock/memory-thread-list-sidebar";
import {
  StockChatPrefsHost,
  useStockChatPrefs,
} from "@digithings/ui/chat/stock";
import { p } from "@/lib/base-path";
import type { DigichatClientConfig } from "@/lib/deploy-config";
import { toStockChatPrefsConfig } from "@/lib/route-client-config";
import {
  takePendingForceTool,
  takePendingTurnMode,
  takePendingWebSearchForce,
} from "@/lib/pending-chat-headers";
import { omitForcedCatalogIds } from "@/lib/deploy-config/force-tool";
import {
  SessionMemoryThreadListAdapter,
  memoryThreadStorageKey,
} from "@/lib/session-memory-thread-list";
import { skinOwnsPageChrome } from "@digithings/ui/chat/skins";
import { PresentationFrame } from "@/components/stock/presentation-frame";
import { EmbedComposerMenu, type ComposerMenuKind } from "@/components/stock/embed-composer-menu";
import {
  connectedMcpConfigs,
  mcpSessionOverlayHeaderValue,
  replaceMcpConfig,
} from "@/components/stock/embed-mcp-flow";
import {
  DEFAULT_LANGUAGE_CODE,
  detectBrowserLanguageCode,
  tryResolveLanguageInput,
} from "@/lib/languages";

/** Prefs deps: the same app functions at both call sites below (WS4 Step 3). */
const PREFS_DEPS = {
  defaultLanguageCode: DEFAULT_LANGUAGE_CODE,
  detectLanguage: detectBrowserLanguageCode,
  resolveLanguage: tryResolveLanguageInput,
  mcpOps: {
    replace: replaceMcpConfig,
    connected: connectedMcpConfigs,
    headerValue: mcpSessionOverlayHeaderValue,
  },
  renderMenuPanes: (menu: {
    kind: ComposerMenuKind;
    models: readonly string[];
    providerSeed?: string;
    mcpSeed?: string;
    onClose: () => void;
  }) => (
    <EmbedComposerMenu
      kind={menu.kind}
      models={menu.models}
      onClose={menu.onClose}
      providerSeed={menu.providerSeed}
      mcpSeed={menu.mcpSeed}
    />
  ),
};



function useShellThreadRuntime(
  clientConfig: DigichatClientConfig,
  sessionKey: string,
  getLanguage: () => string,
  getModel: () => string | undefined,
  getDisabledTools: () => string,
  getEnableWebSearch: () => boolean,
  getMcpSession: () => string | undefined,
  getEffort: () => string | undefined,
) {
  const transport = useMemo(
    () =>
      new AssistantChatTransport<UIMessage>({
        api: p("/api/chat"),
        credentials: "include",
        prepareSendMessagesRequest: ({ messages, id, body, headers }) => {
          const h = new Headers(headers as HeadersInit | undefined);
          const threadKey = typeof id === "string" && id ? id : sessionKey;
          h.set("X-Digichat-Session", threadKey);
          const turnMode = takePendingTurnMode(threadKey);
          if (turnMode) h.set("X-Digi-Turn-Mode", turnMode);
          // Slash remainder-force is armed on prefs sessionKey (`app:anon`),
          // not the AI SDK chat `id` (#3741 review).
          const forceTool = takePendingForceTool(sessionKey);
          if (forceTool && !turnMode) h.set("X-Digi-Force-Tool", forceTool);
          h.set("X-Digi-Run-Id", crypto.randomUUID());
          const lang = getLanguage().trim();
          if (lang && lang !== "en") h.set("X-Digi-Language", lang);
          const model = getModel()?.trim();
          if (model) h.set("X-Digi-Model", model);
          const forceWeb = takePendingWebSearchForce(sessionKey);
          if (getEnableWebSearch() || forceWeb) {
            h.set("X-Digi-Enable-Web-Search", "1");
          }
          const disabled = omitForcedCatalogIds(
            getDisabledTools()
              .split(",")
              .map((s) => s.trim())
              .filter(Boolean),
            forceTool,
          );
          if (disabled.length) h.set("X-Digi-Disabled-Tools", disabled.join(","));
          const mcpSession = getMcpSession()?.trim();
          if (mcpSession) h.set("X-Digi-Mcp-Session", mcpSession);
          const effort = getEffort()?.trim().toLowerCase();
          if (effort === "low" || effort === "medium" || effort === "high") {
            h.set("X-Digi-Effort", effort);
          }
          return {
            body: {
              ...(typeof body === "object" && body !== null ? body : {}),
              id,
              messages,
            },
            headers: h,
          };
        },
      }),
    [sessionKey, getLanguage, getModel, getDisabledTools, getEnableWebSearch, getMcpSession, getEffort],
  );

  const chat = useChat<UIMessage>({ transport });
  const adapters = useMemo(
    () => buildProductRuntimeAdapters(clientConfig.features),
    [clientConfig.features],
  );
  return useAISDKRuntime(chat, { adapters });
}

function HomeStockClientSingle({
  clientConfig,
  userId,
}: {
  clientConfig: DigichatClientConfig;
  userId?: string;
}) {
  const sessionKey = userId ? `app:${userId}` : "app:anon";
  const prefs = useStockChatPrefs({
    config: toStockChatPrefsConfig(clientConfig),
    deps: PREFS_DEPS,
    sessionKey,
    hasSessions: false,
    newThread: () => {},
    redo: () => {},
  });
  const runtime = useShellThreadRuntime(
    clientConfig,
    sessionKey,
    prefs.getLanguage,
    prefs.getModel,
    prefs.getDisabledTools,
    prefs.getEnableWebSearch,
    prefs.getMcpSession,
    prefs.getEffort,
  );

  const mode = clientConfig.chrome.mode;

  return (
    <StockChatPrefsHost value={prefs.prefsApi} panes={prefs.panes}>
      <div
        // `modal` portals its panel to `document.body` (see DigichatLauncher),
        // so this wrapper only sizes the page for the non-framed and sidebar
        // cases — `h-dvh` is right for both.
        className="flex h-dvh flex-col"
        data-chrome-mode={mode}
        data-persistence="none"
      >
        <PresentationFrame mode={mode} clientConfig={clientConfig}>
          <ProductStockShell
            runtime={runtime}
            clientConfig={clientConfig}
            persistence="none"
            sessionKey={sessionKey}
            headerSlot={null}
            onWebSearchChange={prefs.setWebSearch}
          />
        </PresentationFrame>
      </div>
    </StockChatPrefsHost>
  );
}

function HomeStockClientMemory({
  clientConfig,
  userId,
}: {
  clientConfig: DigichatClientConfig;
  userId?: string;
}) {
  const sessionKey = userId ? `app:${userId}` : "app:anon";
  const prefs = useStockChatPrefs({
    config: toStockChatPrefsConfig(clientConfig),
    deps: PREFS_DEPS,
    sessionKey,
    hasSessions: true,
    newThread: () => {},
    redo: () => {},
  });
  const [memoryAdapter] = useState(
    () => new SessionMemoryThreadListAdapter(memoryThreadStorageKey("app", userId)),
  );

  const configRef = useRef(clientConfig);
  // eslint-disable-next-line react-hooks/refs -- useLatest for runtimeHook closures
  configRef.current = clientConfig;
  const sessionRef = useRef(sessionKey);
  // eslint-disable-next-line react-hooks/refs -- useLatest
  sessionRef.current = sessionKey;
  const getLanguageRef = useRef(prefs.getLanguage);
  // eslint-disable-next-line react-hooks/refs -- useLatest
  getLanguageRef.current = prefs.getLanguage;
  const getModelRef = useRef(prefs.getModel);
  // eslint-disable-next-line react-hooks/refs -- useLatest
  getModelRef.current = prefs.getModel;
  const getDisabledRef = useRef(prefs.getDisabledTools);
  // eslint-disable-next-line react-hooks/refs -- useLatest
  getDisabledRef.current = prefs.getDisabledTools;
  const getWebRef = useRef(prefs.getEnableWebSearch);
  // eslint-disable-next-line react-hooks/refs -- useLatest
  getWebRef.current = prefs.getEnableWebSearch;
  const getMcpRef = useRef(prefs.getMcpSession);
  // eslint-disable-next-line react-hooks/refs -- useLatest
  getMcpRef.current = prefs.getMcpSession;
  const getEffortRef = useRef(prefs.getEffort);
  // eslint-disable-next-line react-hooks/refs -- useLatest
  getEffortRef.current = prefs.getEffort;

  const runtimeHook = useMemo(() => {
    return function useMemoryThreadRuntime() {
      return useShellThreadRuntime(
        configRef.current,
        sessionRef.current,
        () => getLanguageRef.current(),
        () => getModelRef.current(),
        () => getDisabledRef.current(),
        () => getWebRef.current(),
        () => getMcpRef.current(),
        () => getEffortRef.current(),
      );
    };
  }, []);

  const runtime = useRemoteThreadListRuntime({
    adapter: memoryAdapter,
    runtimeHook,
  });

  const mode = clientConfig.chrome.mode;

  return (
    <StockChatPrefsHost value={prefs.prefsApi} panes={prefs.panes}>
      <div
        className="flex h-dvh flex-col"
        data-chrome-mode={mode}
        data-persistence="memory"
      >
        <PresentationFrame mode={mode} clientConfig={clientConfig}>
          <ProductStockShell
            runtime={runtime}
            clientConfig={clientConfig}
            persistence="memory"
            sessionKey={sessionKey}
            sideSlot={<MemoryThreadListSidebar />}
            headerSlot={null}
            onWebSearchChange={prefs.setWebSearch}
          />
        </PresentationFrame>
      </div>
    </StockChatPrefsHost>
  );
}

export function HomeStockClient({
  clientConfig,
  userId,
}: {
  clientConfig: DigichatClientConfig;
  userId?: string;
}) {
  if (
    clientConfig.persistence === "memory" &&
    !skinOwnsPageChrome(clientConfig.chrome.skin)
  ) {
    return (
      <HomeStockClientMemory clientConfig={clientConfig} userId={userId} />
    );
  }
  return <HomeStockClientSingle clientConfig={clientConfig} userId={userId} />;
}
