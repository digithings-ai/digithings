"use client";

import { useCallback, useEffect, useMemo } from "react";
import { useChat } from "@ai-sdk/react";
import { DefaultChatTransport, type UIMessage } from "ai";
import type { DigiChatActivity, DigiChatController, DigiChatMessage } from "@digithings/digichat-ui";
import { formatEmbedChatError } from "@/lib/embed-chat-error";
import { p } from "@/lib/base-path";
import { resolveEmbedHost } from "@/lib/embed-gate";

/** Read ?token= / ?host= at send time — useChat transport is frozen on first render (#1339). */
function readEmbedUrlAuth(): { token?: string; host?: string } {
  if (typeof window === "undefined") return {};
  const params = new URLSearchParams(window.location.search);
  const token = params.get("token")?.trim();
  const host = params.get("host")?.trim();
  return {
    token: token || undefined,
    host: host || undefined,
  };
}

const CONVERSATION_STORAGE_PREFIX = "digichat_embed_conversation:";

function conversationStorageKey(host: string): string {
  return `${CONVERSATION_STORAGE_PREFIX}${host}`;
}

type TracePartData = {
  type?: string;
  payload?: { label?: unknown; status?: unknown };
};

export function uiMessageToDigiChat(message: UIMessage): DigiChatMessage {
  const text = message.parts
    .filter((part): part is { type: "text"; text: string } => part.type === "text")
    .map((part) => part.text)
    .join("");

  const traces = message.parts.filter(
    (part): part is { type: "data-digigraphTrace"; data: TracePartData } =>
      part.type === "data-digigraphTrace",
  );

  // Collapse trace steps by label: the external relay can emit the same step
  // more than once (e.g. repeated "in_progress" frames), and each trace part
  // carries a unique id so nothing reconciles upstream. Keyed by resolved
  // label, first-seen order preserved; `done` is true if any frame completed.
  const byLabel = new Map<string, { label: string; done: boolean }>();
  for (const t of traces) {
    const label = String(t.data?.payload?.label ?? t.data?.type ?? "activity");
    const done = t.data?.payload?.status === "completed";
    const seen = byLabel.get(label);
    if (seen) seen.done = seen.done || done;
    else byLabel.set(label, { label, done });
  }

  const activities: DigiChatActivity[] = Array.from(byLabel.values(), (t) => ({
    kind: "trace" as const,
    label: t.label,
    done: t.done,
  }));

  return {
    role: message.role === "user" ? "user" : "assistant",
    content: text,
    activities: activities.length ? activities : undefined,
  };
}

type UseEmbedDigiChatOptions = {
  accent: string;
  token?: string;
  host?: string;
  embedHost: string;
  byokKey?: string;
  byokProvider?: string;
  byokModel?: string;
};

export function useEmbedDigiChat({
  accent,
  token,
  host,
  embedHost,
  byokKey,
  byokProvider,
  byokModel,
}: UseEmbedDigiChatOptions): DigiChatController {
  const transport = useMemo(
    () =>
      new DefaultChatTransport({
        api: p("/api/chat"),
        prepareSendMessagesRequest: ({ messages, body }) => {
          const urlAuth = readEmbedUrlAuth();
          const effectiveToken = urlAuth.token ?? token;
          const effectiveHost = urlAuth.host ?? host;
          const resolvedHost = resolveEmbedHost(effectiveHost) || embedHost;
          const headers: Record<string, string> = {
            "content-type": "application/json",
            "X-Embed-Host": resolvedHost,
            "X-Embed-Accent": accent,
          };
          if (effectiveToken) headers["X-Embed-Token"] = effectiveToken;
          if (byokKey) {
            headers["X-BYOK-Key"] = byokKey;
            headers["X-BYOK-Provider"] = byokProvider ?? "openrouter";
            if (byokProvider === "openrouter" && byokModel?.trim()) {
              headers["X-BYOK-Model"] = byokModel.trim();
            }
          }
          try {
            const conversationId = window.sessionStorage.getItem(
              conversationStorageKey(resolvedHost),
            );
            if (conversationId) headers["X-External-Conversation"] = conversationId;
          } catch {
            /* sessionStorage unavailable */
          }
          return {
            body: {
              ...(typeof body === "object" && body !== null ? body : {}),
              messages,
            },
            headers,
          };
        },
      }),
    [accent, token, host, embedHost, byokKey, byokProvider, byokModel],
  );

  const { messages, sendMessage, status, error, regenerate } = useChat<UIMessage>({
    transport,
  });

  useEffect(() => {
    const last = messages[messages.length - 1];
    if (!last || last.role !== "assistant") return;
    for (const part of last.parts) {
      if (part.type === "data-externalConversation") {
        const id = (part as { data?: { conversationId?: string } }).data?.conversationId;
        if (id) {
          try {
            window.sessionStorage.setItem(conversationStorageKey(embedHost), id);
          } catch {
            /* ignore */
          }
        }
      }
    }
  }, [messages, embedHost]);

  const busy = status === "streaming" || status === "submitted";
  const chatError = formatEmbedChatError(error);

  const send = useCallback(
    (question: string) => {
      const q = question.trim();
      if (!q || busy) return;
      sendMessage({
        role: "user",
        parts: [{ type: "text", text: q }],
      });
    },
    [busy, sendMessage],
  );

  const digiMessages = useMemo(() => messages.map(uiMessageToDigiChat), [messages]);

  return {
    messages: digiMessages,
    busy,
    error: chatError,
    send,
    onRetry: () => regenerate(),
  };
}
