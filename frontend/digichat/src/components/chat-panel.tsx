"use client";

/** First-party chat host: transport, persistence, BYOK. Stock Thread via ProductStockShell. */

import { useMemo, useState } from "react";
import { useChat } from "@ai-sdk/react";
import type { UIMessage } from "ai";
import { AssistantChatTransport, useAISDKRuntime } from "@assistant-ui/ai-sdk";
import { QuantComparisonStrip } from "@/components/quant-comparison-strip";
import { ByokCliFlow } from "@/components/byok-cli-flow";
import {
  ProductStockShell,
  buildProductRuntimeAdapters,
} from "@/components/stock/product-shell";
import { ToolCatalogBar } from "@/components/stock/tool-catalog-bar";
import { p } from "@/lib/base-path";
import { useBYOKKey } from "@/hooks/use-byok-key";
import {
  isWebSearchEnabled,
  readWebSearchPref,
  writeWebSearchPref,
} from "@/lib/web-search-pref";
import {
  takePendingForceTool,
  takePendingTurnMode,
} from "@/lib/pending-chat-headers";
import {
  DEFAULT_CLIENT_CONFIG,
  type DigichatClientConfig,
} from "@/lib/deploy-config";
import { skinOwnsPageChrome } from "@/lib/thread-skins";

type SystemNote = { id: string; text: string };

export type ChatPanelProps = {
  threadId: string;
  threadTitle: string;
  initialMessages: UIMessage[];
  onMessagesCommit: (threadId: string, messages: UIMessage[]) => void;
  onTitleDerived?: (threadId: string, title: string) => void;
  onAllowTruncate?: (threadId: string) => void;
  headerSlot?: React.ReactNode;
  byokMode?: boolean;
  onByokModeChange?: (open: boolean) => void;
  /** Deploy client projection (features, tools, chrome). */
  clientConfig?: DigichatClientConfig;
};

function messagePlainText(message: UIMessage): string {
  return (message.parts ?? [])
    .filter((p): p is { type: "text"; text: string } => p.type === "text")
    .map((p) => p.text)
    .join("");
}

export function ChatPanel({
  threadId,
  threadTitle,
  initialMessages,
  onMessagesCommit,
  onTitleDerived,
  onAllowTruncate,
  headerSlot,
  byokMode = false,
  onByokModeChange,
  clientConfig = DEFAULT_CLIENT_CONFIG,
}: ChatPanelProps) {
  const [systemNotes, setSystemNotes] = useState<SystemNote[]>([]);
  const {
    key: byokKey,
    provider: byokProvider,
    model: byokModel,
    isSet: byokIsSet,
    setKey: setByokKey,
    clearKey: clearByokKey,
  } = useBYOKKey();

  const webSearchAllowed =
    clientConfig.gate.webSearch === true ||
    clientConfig.tools.catalog.some((t) => t.id === "web_search") ||
    (typeof process.env.NEXT_PUBLIC_DIGICHAT_WEB_SEARCH === "string" &&
      process.env.NEXT_PUBLIC_DIGICHAT_WEB_SEARCH === "1");
  const [webSearchPref, setWebSearchPref] = useState(() =>
    webSearchAllowed && typeof window !== "undefined" ? readWebSearchPref("auth") : false,
  );

  const transport = useMemo(
    () =>
      new AssistantChatTransport<UIMessage>({
        api: p("/api/chat"),
        credentials: "include",
        prepareSendMessagesRequest: ({ messages, id, body, headers }) => {
          const h = new Headers(headers as HeadersInit | undefined);
          h.set("X-Digichat-Session", threadId);
          const turnMode = takePendingTurnMode(threadId);
          if (turnMode) {
            h.set("X-Digi-Turn-Mode", turnMode);
          }
          const forceTool = takePendingForceTool(threadId);
          if (forceTool && !turnMode) {
            h.set("X-Digi-Force-Tool", forceTool);
          }
          h.set("X-Digi-Run-Id", crypto.randomUUID());
          if (
            webSearchAllowed &&
            isWebSearchEnabled({ tenantAllows: true, userPref: webSearchPref })
          ) {
            h.set("X-Digi-Enable-Web-Search", "1");
          }
          if (byokKey) {
            h.set("X-BYOK-Key", byokKey);
            h.set("X-BYOK-Provider", byokProvider);
            if (byokModel.trim()) {
              h.set("X-BYOK-Model", byokModel.trim());
            }
          }
          return {
            body: { ...(typeof body === "object" && body !== null ? body : {}), id, messages },
            headers: h,
          };
        },
      }),
    [threadId, byokKey, byokProvider, byokModel, webSearchAllowed, webSearchPref],
  );

  const chat = useChat<UIMessage>({
    id: threadId,
    messages: initialMessages,
    transport,
    onFinish: ({ messages: next }) => {
      onMessagesCommit(threadId, next);
      const userTexts = next
        .filter((m) => m.role === "user")
        .map(messagePlainText)
        .filter(Boolean);
      const first = userTexts[0];
      if (first && (threadTitle === "New chat" || threadTitle.trim() === "") && onTitleDerived) {
        const t = first.slice(0, 52) + (first.length > 52 ? "…" : "");
        onTitleDerived(threadId, t);
      }
    },
  });
  const { messages, error } = chat;
  const runtimeAdapters = useMemo(
    () => buildProductRuntimeAdapters(clientConfig.features),
    [clientConfig.features],
  );
  const runtime = useAISDKRuntime(chat, { adapters: runtimeAdapters });

  const persistence =
    clientConfig.persistence === "server" || clientConfig.persistence === "memory"
      ? clientConfig.persistence
      : "none";

  return (
    <>
      <ProductStockShell
        runtime={runtime}
        clientConfig={clientConfig}
        persistence={persistence === "server" ? "none" : persistence}
        headerSlot={
          skinOwnsPageChrome(clientConfig.chrome.skin) ? null : (
          <>
            {headerSlot}
            <ToolCatalogBar
              clientConfig={clientConfig}
              sessionKey={threadId}
              onWebSearchChange={(on) => {
                writeWebSearchPref("auth", on);
                setWebSearchPref(on);
              }}
            />
            {systemNotes.length > 0 ? (
              <div className="space-y-1 px-3 py-2 text-xs text-muted-foreground">
                {systemNotes.map((n) => (
                  <div key={n.id}>{n.text}</div>
                ))}
              </div>
            ) : null}
          </>
          )
        }
        footerSlot={
          <>
            {error?.message ? (
              <div role="alert" className="px-3 py-2 text-sm text-destructive">
                {error.message}
              </div>
            ) : null}
            <QuantComparisonStrip messages={messages} conversationId={threadId} />
          </>
        }
      />
      {byokMode ? (
        <div
          className="fixed inset-x-0 bottom-0 z-50 border-t border-border bg-background p-3 shadow-lg"
          role="dialog"
          aria-label="BYOK"
        >
          <ByokCliFlow
            onClose={() => onByokModeChange?.(false)}
            onActivate={(key, provider, model) => {
              setByokKey(key, provider, model);
              onByokModeChange?.(false);
            }}
            onClear={clearByokKey}
            active={byokIsSet ? { provider: byokProvider, model: byokModel } : null}
            initialProvider={byokProvider}
            initialModel={byokModel}
          />
        </div>
      ) : null}
    </>
  );
}
