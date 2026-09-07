"use client";

/**
 * Anonymous / memory app shell: stock Thread → POST /api/chat.
 * persistence=memory: useRemoteThreadListRuntime + SessionMemoryThreadListAdapter
 * and ThreadListPrimitive sidebar (inside the runtime provider).
 */

import { useCallback, useMemo, useRef, useState } from "react";
import { useChat } from "@ai-sdk/react";
import type { UIMessage } from "ai";
import { AssistantChatTransport, useAISDKRuntime } from "@assistant-ui/ai-sdk";
import { useRemoteThreadListRuntime } from "@assistant-ui/react";
import {
  ProductStockShell,
  buildProductRuntimeAdapters,
} from "@/components/stock/product-shell";
import { MemoryThreadListSidebar } from "@/components/stock/memory-thread-list-sidebar";
import { p } from "@/lib/base-path";
import type { DigichatClientConfig } from "@/lib/deploy-config";
import {
  takePendingForceTool,
  takePendingTurnMode,
} from "@/lib/pending-chat-headers";
import {
  SessionMemoryThreadListAdapter,
  memoryThreadStorageKey,
} from "@/lib/session-memory-thread-list";
import { detectBrowserLanguageCode } from "@/lib/languages";
import { skinOwnsPageChrome } from "@/lib/thread-skins";

function useShellThreadRuntime(
  clientConfig: DigichatClientConfig,
  sessionKey: string,
  getLanguage: () => string,
  getModel: () => string | undefined,
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
          const forceTool = takePendingForceTool(threadKey);
          if (forceTool && !turnMode) h.set("X-Digi-Force-Tool", forceTool);
          h.set("X-Digi-Run-Id", crypto.randomUUID());
          const lang = getLanguage().trim();
          if (lang && lang !== "en") h.set("X-Digi-Language", lang);
          const model = getModel()?.trim();
          if (model) h.set("X-Digi-Model", model);
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
    [sessionKey, getLanguage, getModel],
  );

  const chat = useChat<UIMessage>({ transport });
  const adapters = useMemo(
    () => buildProductRuntimeAdapters(clientConfig.features),
    [clientConfig.features],
  );
  return useAISDKRuntime(chat, { adapters });
}

function useDeployChromeState(clientConfig: DigichatClientConfig) {
  const [language, setLanguage] = useState(
    () => clientConfig.chrome.defaultLanguage || detectBrowserLanguageCode(),
  );
  const [model, setModel] = useState(
    () => clientConfig.models.default ?? clientConfig.models.available[0] ?? "",
  );
  const languageRef = useRef(language);
  const modelRef = useRef(model);
  languageRef.current = language;
  modelRef.current = model;
  const getLanguage = useCallback(() => languageRef.current, []);
  const getModel = useCallback(() => {
    const id = modelRef.current.trim();
    return id || undefined;
  }, []);
  const showLanguage = clientConfig.gate.showLanguageSelector === true;
  const showModelPicker = clientConfig.models.allowPicker === true;
  return {
    language,
    setLanguage: showLanguage ? setLanguage : undefined,
    model,
    setModel: showModelPicker ? setModel : undefined,
    models: showModelPicker ? clientConfig.models.available : undefined,
    getLanguage,
    getModel,
  };
}

function HomeStockClientSingle({
  clientConfig,
  userId,
}: {
  clientConfig: DigichatClientConfig;
  userId?: string;
}) {
  const sessionKey = userId ? `app:${userId}` : "app:anon";
  const chrome = useDeployChromeState(clientConfig);
  const runtime = useShellThreadRuntime(
    clientConfig,
    sessionKey,
    chrome.getLanguage,
    chrome.getModel,
  );

  return (
    <div
      className="flex h-dvh flex-col"
      data-chrome-mode="app"
      data-persistence="none"
    >
      <ProductStockShell
        runtime={runtime}
        clientConfig={clientConfig}
        persistence="none"
        headerSlot={null}
      />
    </div>
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
  const chrome = useDeployChromeState(clientConfig);
  const adapterRef = useRef<SessionMemoryThreadListAdapter | null>(null);
  if (!adapterRef.current) {
    adapterRef.current = new SessionMemoryThreadListAdapter(
      memoryThreadStorageKey("app", userId),
    );
  }

  const configRef = useRef(clientConfig);
  configRef.current = clientConfig;
  const sessionRef = useRef(sessionKey);
  sessionRef.current = sessionKey;
  const getLanguageRef = useRef(chrome.getLanguage);
  getLanguageRef.current = chrome.getLanguage;
  const getModelRef = useRef(chrome.getModel);
  getModelRef.current = chrome.getModel;

  const runtimeHook = useMemo(() => {
    return function useMemoryThreadRuntime() {
      return useShellThreadRuntime(
        configRef.current,
        sessionRef.current,
        () => getLanguageRef.current(),
        () => getModelRef.current(),
      );
    };
  }, []);

  const runtime = useRemoteThreadListRuntime({
    adapter: adapterRef.current,
    runtimeHook,
  });

  return (
    <div
      className="flex h-dvh flex-col"
      data-chrome-mode="app"
      data-persistence="memory"
    >
      <ProductStockShell
        runtime={runtime}
        clientConfig={clientConfig}
        persistence="memory"
        sideSlot={<MemoryThreadListSidebar />}
        headerSlot={null}
      />
    </div>
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
