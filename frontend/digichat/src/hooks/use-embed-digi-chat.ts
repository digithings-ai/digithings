"use client";

import { useCallback, useEffect, useMemo, useRef } from "react";
import { useChat } from "@ai-sdk/react";
import { DefaultChatTransport, type UIMessage } from "ai";
import type { DigiChatActivity, DigiChatController, DigiChatMessage } from "@digithings/digichat-ui";
import { formatEmbedChatError } from "@/lib/embed-chat-error";
import { type BYOKProvider } from "@/hooks/use-byok-key";
import { p } from "@/lib/base-path";
import { readTrialUnlocked, readChatAccessToken, resolveEmbedHost } from "@/lib/embed-gate";
import { resolveLanguageCode } from "@/lib/languages";
import {
  ACTIVITY_PART_TYPE,
  sanitizeActivitySpan,
  toDigiChatActivity,
  type ActivitySpan,
} from "@/lib/chat-activity";

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

/**
 * Whether this embed host is trial-unlocked, read at send time.
 * Same freeze reason as readEmbedUrlAuth (#1339): a `trialUnlocked` prop closed
 * over by DefaultChatTransport stays false after datatap:unlocked arrives, so
 * the client counter can show 100 while the server still returns trial_gate.
 */
export function isEmbedTrialUnlockedAtSend(
  resolvedHost: string,
  propFallback?: boolean,
): boolean {
  return !!propFallback || readTrialUnlocked(resolvedHost);
}

/**
 * The chat-access token for this host, read at send time. Same freeze reason as
 * isEmbedTrialUnlockedAtSend (#1339): a token closed over by DefaultChatTransport would be null
 * forever, because it is written after the transport is created.
 */
export function chatAccessTokenAtSend(resolvedHost: string): string | null {
  return readChatAccessToken(resolvedHost);
}

const CONVERSATION_STORAGE_PREFIX = "digichat_embed_conversation:";

function conversationStorageKey(host: string): string {
  return `${CONVERSATION_STORAGE_PREFIX}${host}`;
}

/** The upstream conversation id for this embed host, when one has been established. */
export function readEmbedConversationId(embedHost: string): string | null {
  try {
    return window.sessionStorage.getItem(conversationStorageKey(embedHost));
  } catch {
    return null;
  }
}

type TracePartData = {
  type?: string;
  payload?: { label?: unknown; status?: unknown };
};

/**
 * Legacy path: providers emitted a single data-digigraphTrace{label,status} part
 * before the activity protocol landed. A visitor's browser caching an OLD client
 * bundle isn't what this covers — that old bundle doesn't contain this function
 * at all, so no branch here could help it. What it actually covers is the
 * reverse: during a rolling deploy, a visitor who has already loaded this NEW
 * client bundle can still be routed to an OLD server revision that hasn't
 * picked up the activity protocol yet and only emits data-digigraphTrace. This
 * fallback keeps that visitor's steps rendering until the rollout finishes.
 * TODO(next release): remove once no server revision can emit the legacy part.
 */
function legacyTraceActivities(message: UIMessage): DigiChatActivity[] {
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

  return Array.from(byLabel.values(), (t) => ({
    kind: "trace" as const,
    label: t.label,
    done: t.done,
  }));
}

export function uiMessageToDigiChat(
  message: UIMessage,
  opts: { settle?: boolean } = {},
): DigiChatMessage {
  const text = message.parts
    .filter((part): part is { type: "text"; text: string } => part.type === "text")
    .map((part) => part.text)
    .join("");

  const spans = message.parts
    .filter((part): part is { type: typeof ACTIVITY_PART_TYPE; data: unknown } =>
      part.type === ACTIVITY_PART_TYPE
    )
    .map((part) => sanitizeActivitySpan(part.data))
    .filter((span): span is ActivitySpan => span !== null);

  // Activity parts win outright: during a deploy a single message could carry
  // both shapes, and rendering both would double every step.
  const hasActivityParts = message.parts.some((part) => part.type === ACTIVITY_PART_TYPE);
  const activities = hasActivityParts
    ? toDigiChatActivity(spans, opts)
    : legacyTraceActivities(message);

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
  trialUnlocked?: boolean;
  onGated?: () => void;
  /**
   * Read at send time inside prepareSendMessagesRequest — same freeze reason
   * as isEmbedTrialUnlockedAtSend/chatAccessTokenAtSend (#1339): the transport
   * is built once in useMemo and useChat never adopts a rebuilt one, so a
   * `responseLanguage: string` prop closed over by value would stay frozen at
   * whatever detectBrowserLanguageCode() returned at mount forever (#2103
   * final review, Critical finding). Unlike those two precedents, the value
   * here must NOT be storage-backed (sessionStorage/localStorage) — the
   * language is session-only and must reset on reload — so the caller passes
   * a stable accessor closing over a ref instead of a storage-read helper.
   */
  getResponseLanguage?: () => string;
};

export function useEmbedDigiChat({
  accent,
  token,
  host,
  embedHost,
  byokKey,
  byokProvider,
  byokModel,
  trialUnlocked,
  onGated,
  getResponseLanguage,
}: UseEmbedDigiChatOptions): DigiChatController & {
  seed: (msgs: readonly DigiChatMessage[]) => void;
  /** Raw AI SDK error — for structured code detection (quota → BYOK). */
  rawError: Error | undefined;
} {
  const pendingForceTool = useRef<string | undefined>(undefined);
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
            const provider = (byokProvider ?? "openrouter") as BYOKProvider;
            headers["X-BYOK-Provider"] = provider;
            // Same as chat-panel: a model the user chose is forwarded whatever the
            // provider's requiresModel flag says (#2490).
            if (byokModel?.trim()) {
              headers["X-BYOK-Model"] = byokModel.trim();
            }
          }
          // Send-time read — same freeze reason as isEmbedTrialUnlockedAtSend/
          // chatAccessTokenAtSend below (#1339): a language value closed over
          // by the transport at creation time would stay frozen at whatever
          // detectBrowserLanguageCode() returned at mount, so `/lang` would
          // never reach the header (#2103 / #3418). Normalize against the
          // curated list before forwarding — defense-in-depth for a hypothetical
          // future caller of this exported hook that doesn't already pass a
          // curated-safe value (see #2103 final review, Fix 6).
          const normalizedLanguage = resolveLanguageCode(getResponseLanguage?.());
          if (normalizedLanguage !== "en") {
            headers["X-Digi-Language"] = normalizedLanguage;
          }
          const forceTool = pendingForceTool.current;
          pendingForceTool.current = undefined;
          if (forceTool) {
            headers["X-Digi-Force-Tool"] = forceTool;
          }
          // Send-time unlock check — transport is frozen on first render (#1339),
          // so a closed-over trialUnlocked prop stays false after datatap:unlocked.
          if (isEmbedTrialUnlockedAtSend(resolvedHost, trialUnlocked)) {
            headers["X-Embed-Trial-Unlock"] = "1";
          }
          const chatToken = chatAccessTokenAtSend(resolvedHost);
          if (chatToken) {
            headers["X-Embed-Chat-Token"] = chatToken;
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
    // trialUnlocked and getResponseLanguage both stay in the deps for the rare
    // case useChat starts honoring transport identity; the send-time read
    // (see the doc comment on getResponseLanguage above) is what actually
    // keeps the outgoing language current today. Keeping getResponseLanguage
    // here costs nothing — the caller builds it with useCallback(() => ...,
    // []), so its identity never changes and the transport is never rebuilt
    // on a language change — while satisfying react-hooks/exhaustive-deps.
    [
      accent,
      token,
      host,
      embedHost,
      byokKey,
      byokProvider,
      byokModel,
      trialUnlocked,
      getResponseLanguage,
    ],
  );

  const { messages, sendMessage, status, error, regenerate, setMessages, stop } = useChat<UIMessage>({
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

  useEffect(() => {
    if (!error?.message || !onGated) return;
    try {
      const parsed = JSON.parse(error.message.trim()) as { error?: string };
      if (parsed.error === "trial_gate") onGated();
    } catch {
      /* non-JSON error — not a gate signal */
    }
  }, [error, onGated]);

  const send = useCallback(
    (question: string, opts?: { forceTool?: string }) => {
      const q = question.trim();
      if (!q || busy) return;
      pendingForceTool.current = opts?.forceTool;
      sendMessage({
        role: "user",
        parts: [{ type: "text", text: q }],
      });
    },
    [busy, sendMessage],
  );

  const reset = useCallback(() => {
    setMessages([]);
  }, [setMessages]);

  // Mid-stream: keep completed searches as running tool_call rows until
  // retrieve arrives (or the turn settles). Settling early flashes "no hits".
  const digiMessages = useMemo(
    () =>
      messages.map((m, i) => {
        const streamingTurn = busy && i === messages.length - 1 && m.role === "assistant";
        return uiMessageToDigiChat(m, { settle: !streamingTurn });
      }),
    [messages, busy],
  );

  const seed = useCallback(
    (msgs: readonly DigiChatMessage[]) => {
      setMessages(
        msgs.map((m) => ({
          id: crypto.randomUUID(),
          role: m.role,
          parts: [{ type: "text" as const, text: m.content }],
        })),
      );
    },
    [setMessages],
  );

  return {
    messages: digiMessages,
    busy,
    error: chatError,
    /** Raw AI SDK error — for structured code detection (quota → BYOK). */
    rawError: error,
    send,
    reset,
    stop: () => {
      void stop();
    },
    onRetry: () => {
      void regenerate();
    },
    seed,
  };
}
