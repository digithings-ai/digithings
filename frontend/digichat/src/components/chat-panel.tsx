"use client";

/** First-party chat host: transport, persistence, BYOK. Transcript/composer live in CliThread. */

import { useCallback, useMemo, useState } from "react";
import { useChat } from "@ai-sdk/react";
import type { UIMessage } from "ai";
import { AssistantChatTransport, useAISDKRuntime } from "@assistant-ui/ai-sdk";
import { AssistantRuntimeProvider } from "@assistant-ui/react";
import { QuantComparisonStrip } from "@/components/quant-comparison-strip";
import { ByokCliFlow } from "@/components/byok-cli-flow";
import { CliThread } from "@/components/assistant-ui/cli-thread";
import { p } from "@/lib/base-path";
import { useBYOKKey } from "@/hooks/use-byok-key";
import {
  isWebSearchEnabled,
  readWebSearchPref,
  writeWebSearchPref,
} from "@/lib/web-search-pref";
import {
  setPendingForceTool,
  setPendingTurnMode,
  takePendingForceTool,
  takePendingTurnMode,
} from "@/lib/pending-chat-headers";

const APP_SLASH_EXTRA: Array<{ cmd: string; hint: string }> = [
  { cmd: "/clear", hint: "clear thread" },
  { cmd: "/history", hint: "focus sidebar" },
  { cmd: "/scope", hint: "show JWT scopes" },
  { cmd: "/model", hint: "model via /byok" },
];

type SystemNote = { id: string; text: string };

export type ChatPanelProps = {
  threadId: string;
  threadTitle: string;
  initialMessages: UIMessage[];
  onMessagesCommit: (threadId: string, messages: UIMessage[]) => void;
  onTitleDerived?: (threadId: string, title: string) => void;
  /**
   * Mark the next server flush as an intentional truncate (edit last user).
   * Without this, PUT returns 409 `would_truncate` (#3466).
   */
  onAllowTruncate?: (threadId: string) => void;
  headerSlot?: React.ReactNode;
  byokMode?: boolean;
  onByokModeChange?: (open: boolean) => void;
  /**
   * Slash-command hook. Receives the raw text (starts with `/`).
   * Return true if the command was handled — the panel will NOT send it
   * to the chat transport. Return false to fall through to the panel's
   * own handling (unknown commands render as a system note).
   */
  onSlashCommand?: (raw: string) => boolean;
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
  onSlashCommand,
}: ChatPanelProps) {
  const [systemNotes, setSystemNotes] = useState<SystemNote[]>([]);
  const [cliSettingsOpen, setCliSettingsOpen] = useState(false);
  const [cliSettingsIndex, setCliSettingsIndex] = useState(0);
  const {
    key: byokKey,
    provider: byokProvider,
    model: byokModel,
    isSet: byokIsSet,
    setKey: setByokKey,
    clearKey: clearByokKey,
  } = useBYOKKey();

  const webSearchAllowed =
    typeof process.env.NEXT_PUBLIC_DIGICHAT_WEB_SEARCH === "string" &&
    process.env.NEXT_PUBLIC_DIGICHAT_WEB_SEARCH === "1";
  const [webSearchPref, setWebSearchPref] = useState(() =>
    webSearchAllowed && typeof window !== "undefined" ? readWebSearchPref("auth") : false,
  );
  if (typeof window !== "undefined" && webSearchAllowed) {
    const stored = readWebSearchPref("auth");
    if (stored !== webSearchPref && !webSearchPref && stored) {
      setWebSearchPref(stored);
    }
  }

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
  const { messages, sendMessage, status, error, regenerate, setMessages } = chat;
  const runtime = useAISDKRuntime(chat);
  const busy = status === "streaming" || status === "submitted";

  const pushSystemNote = useCallback((msg: string) => {
    setSystemNotes((prev) => [...prev, { id: crypto.randomUUID(), text: msg }]);
  }, []);

  const onRegenerate = useCallback(() => {
    setPendingForceTool(threadId);
    setPendingTurnMode(threadId, "regenerate");
    void regenerate();
  }, [regenerate, threadId]);

  const onEditLastUser = useCallback(
    (text: string) => {
      const next = text.trim();
      if (!next || busy) return;
      let lastUserIdx = -1;
      for (let i = messages.length - 1; i >= 0; i--) {
        if (messages[i]?.role === "user") {
          lastUserIdx = i;
          break;
        }
      }
      if (lastUserIdx < 0) return;
      onAllowTruncate?.(threadId);
      setMessages(messages.slice(0, lastUserIdx));
      setPendingForceTool(threadId);
      setPendingTurnMode(threadId, "edit_last_user");
      void sendMessage({
        role: "user",
        parts: [{ type: "text", text: next }],
      });
    },
    [busy, messages, onAllowTruncate, sendMessage, setMessages, threadId],
  );

  const handleSlash = useCallback(
    (raw: string): boolean => {
      const [rawName] = raw.split(/\s+/);
      const name = rawName.toLowerCase();
      if (name === "/scope") {
        pushSystemNote("scope: (signed-in session) — scope surfacing lands with SSO in #202.");
        return true;
      }
      if (name === "/model") {
        pushSystemNote("model selector is part of /byok.");
        return true;
      }
      if (name === "/websearch") {
        if (!webSearchAllowed) {
          pushSystemNote("Web search is not enabled for this tenant.");
          return true;
        }
        const next = !webSearchPref;
        writeWebSearchPref("auth", next);
        setWebSearchPref(next);
        pushSystemNote(`Web search ${next ? "on" : "off"} (External cites).`);
        return true;
      }
      if (onSlashCommand?.(raw)) return true;
      return false;
    },
    [onSlashCommand, pushSystemNote, webSearchAllowed, webSearchPref],
  );

  return (
    <AssistantRuntimeProvider runtime={runtime}>
      <CliThread
        headerSlot={headerSlot}
        extraSlash={APP_SLASH_EXTRA}
        slashVisibility={{ webSearch: webSearchAllowed, byok: true }}
        onSlashCommand={handleSlash}
        onOpenSettings={() => {
          setCliSettingsOpen(true);
          setCliSettingsIndex(0);
        }}
        onByok={() => onByokModeChange?.(true)}
        allowTurnMutation
        onRegenerate={onRegenerate}
        onEditLastUser={onEditLastUser}
        systemNotes={systemNotes}
        errorText={error?.message ?? null}
        disabled={byokMode}
        belowViewportSlot={<QuantComparisonStrip messages={messages} conversationId={threadId} />}
        settingsPanel={
          byokMode ? (
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
          ) : cliSettingsOpen ? (
            <div className="dc-term-row dc-term-row-assistant" role="dialog" aria-label="Settings">
              <span className="dc-term-marker">▸</span>
              <div className="dc-term-body flex flex-col gap-1 font-mono text-xs" style={{ color: "var(--text-secondary)" }}>
                <div>settings</div>
                {webSearchAllowed ? (
                  <button
                    type="button"
                    className="text-left"
                    onClick={() => {
                      const next = !webSearchPref;
                      writeWebSearchPref("auth", next);
                      setWebSearchPref(next);
                    }}
                    onMouseEnter={() => setCliSettingsIndex(0)}
                  >
                    {cliSettingsIndex === 0 ? "> " : "  "}[websearch {webSearchPref ? "on" : "off"}] Web search — External cites
                  </button>
                ) : null}
                <button
                  type="button"
                  className="text-left"
                  onClick={() => {
                    setCliSettingsOpen(false);
                    onByokModeChange?.(true);
                  }}
                  onMouseEnter={() => setCliSettingsIndex(webSearchAllowed ? 1 : 0)}
                >
                  {cliSettingsIndex === (webSearchAllowed ? 1 : 0) ? "> " : "  "}BYOK → {byokIsSet ? "update" : "configure"} — /byok
                </button>
                <div className="opacity-70">click a row · Esc on composer to close</div>
              </div>
            </div>
          ) : null
        }
      />
    </AssistantRuntimeProvider>
  );
}
