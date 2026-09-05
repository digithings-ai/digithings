"use client";

/** Terminal-styled chat pane — `useChat` transport, markdown/trace/chart parts, slash commands. */

import {
  useCallback,
  useEffect,
  useLayoutEffect,
  useMemo,
  useRef,
  useState,
} from "react";
import { useChat } from "@ai-sdk/react";
import {
  isReasoningUIPart,
  isTextUIPart,
  type UIMessage,
} from "ai";
import { AssistantChatTransport, useAISDKRuntime } from "@assistant-ui/ai-sdk";
import { AssistantRuntimeProvider, ThreadPrimitive } from "@assistant-ui/react";
import { ArrowDown, Copy, RefreshCw, Square, Wrench, Key } from "lucide-react";
import { Button } from "@/components/ui/button";
import {
  Collapsible,
  CollapsibleContent,
  CollapsibleTrigger,
} from "@/components/ui/collapsible";
import { QuantComparisonStrip } from "@/components/quant-comparison-strip";
import { ByokCliFlow } from "@/components/byok-cli-flow";
import { EChartsCard } from "@/components/echarts-card";
import { parseChartEnvelope } from "@/lib/chart-spec";
import { p } from "@/lib/base-path";
import { ACTIVITY_PART_TYPE, messageActivities } from "@/lib/chat-activity";
import { useBYOKKey } from "@/hooks/use-byok-key";
import {
  isWebSearchEnabled,
  readWebSearchPref,
  writeWebSearchPref,
} from "@/lib/web-search-pref";
import { cn } from "@/lib/utils";
import { ChatActivities, citationHits, copyMarkdownWithFallback, downloadMarkdown, matchingSlashCommands, nextPaletteIndex, parseSlashInput, serializeAssistantMarkdown, serializeThreadMarkdown } from "@digithings/digichat-ui";
import { ChatMarkdown, type CodeBlockOverride } from "@digithings/web";

const APP_SLASH_EXTRA: Array<{ cmd: string; hint: string }> = [
  { cmd: "/clear", hint: "clear thread" },
  { cmd: "/history", hint: "focus sidebar" },
  { cmd: "/scope", hint: "show JWT scopes" },
  { cmd: "/model", hint: "model via /byok" },
];

/** Per-thread pending turn mode — module map, not a ref (#3475 / #1339). */
const pendingTurnModeByThread = new Map<string, "regenerate" | "edit_last_user">();
const pendingForceByThread = new Map<string, string>();

function setPendingTurnMode(threadId: string, mode?: "regenerate" | "edit_last_user"): void {
  const key = threadId.trim();
  if (!key) return;
  if (mode) pendingTurnModeByThread.set(key, mode);
  else pendingTurnModeByThread.delete(key);
}

function takePendingTurnMode(threadId: string): "regenerate" | "edit_last_user" | undefined {
  const key = threadId.trim();
  const mode = pendingTurnModeByThread.get(key);
  pendingTurnModeByThread.delete(key);
  return mode;
}

function setPendingForceTool(threadId: string, tool?: string): void {
  const key = threadId.trim();
  if (!key) return;
  if (tool) pendingForceByThread.set(key, tool);
  else pendingForceByThread.delete(key);
}

function takePendingForceTool(threadId: string): string | undefined {
  const key = threadId.trim();
  const tool = pendingForceByThread.get(key);
  pendingForceByThread.delete(key);
  return tool;
}

const MAX_INPUT_LINES = 5;

// The one digichat-specific fence shape the shared <ChatMarkdown> renderer
// (also used by digichat's own /embed, digithings-web, and digiweb — mermaid,
// syntax-highlighted code with copy, LaTeX) has no reason to know about: a
// ```json block whose content parses as a chart envelope renders as a live
// chart instead of source text. Everything else — including a ```json block
// that is NOT a chart spec — falls through to the shared renderer's own
// default handling (undefined return), which now means it gets real syntax
// highlighting instead of the bare, unstyled <code> this used to render.
const renderChartCodeBlock: CodeBlockOverride = (lang, code) => {
  if (lang !== "json") return undefined;
  const spec = parseChartEnvelope(code);
  return spec ? <EChartsCard spec={spec} /> : undefined;
};

function messagePlainText(message: UIMessage): string {
  if (!message.parts?.length) return "";
  return message.parts.filter(isTextUIPart).map((p) => p.text).join("");
}

function toolLabel(part: unknown): string {
  if (part && typeof part === "object" && "toolName" in part) {
    const n = (part as { toolName?: string }).toolName;
    if (typeof n === "string" && n) return n;
  }
  if (part && typeof part === "object" && "type" in part) {
    return String((part as { type: string }).type);
  }
  return "Tool";
}

function MessageBody({ message, isStreaming }: { message: UIMessage; isStreaming?: boolean }) {
  if (message.role === "user") {
    const text = messagePlainText(message);
    return (
      <ChatMarkdown
        source={text}
        renderCodeBlock={renderChartCodeBlock}
        className="text-[var(--text-primary)]"
      />
    );
  }

  const activities = messageActivities(message);
  return (
    <div className="space-y-3">
      {activities.length ? <ChatActivities activities={activities} /> : null}
      {message.parts.map((part, i) => {
        const isLast = i === message.parts.length - 1;
        if (part.type === ACTIVITY_PART_TYPE || part.type === "data-digigraphTrace") return null;
        if (isReasoningUIPart(part)) {
          return (
            <Collapsible key={i} className="rounded-none border border-border/60 bg-muted/30">
              <CollapsibleTrigger className="flex w-full cursor-pointer items-center px-3 py-2 text-left text-xs font-medium uppercase tracking-wide text-muted-foreground hover:bg-muted/50">
                Reasoning
              </CollapsibleTrigger>
              <CollapsibleContent>
                <pre className="max-h-64 overflow-auto whitespace-pre-wrap border-t border-border/40 px-3 py-2 font-mono text-xs leading-relaxed text-muted-foreground">
                  {part.text}
                </pre>
              </CollapsibleContent>
            </Collapsible>
          );
        }
        if (isTextUIPart(part)) {
          return (
            <ChatMarkdown
              key={i}
              source={part.text}
              renderCodeBlock={renderChartCodeBlock}
              className={cn(
                "text-[var(--text-primary)]",
                isLast && isStreaming && "dc-term-streaming",
              )}
            />
          );
        }
        if (part.type === "tool-invocation" || part.type === "dynamic-tool") {
          const label = toolLabel(part);
          return (
            <Collapsible key={i} className="overflow-hidden">
              <CollapsibleTrigger className="dc-term-chip cursor-pointer">
                <Wrench className="size-3 shrink-0 opacity-80" />
                <span className="truncate">{label}</span>
              </CollapsibleTrigger>
              <CollapsibleContent>
                <pre className="mt-2 max-h-56 overflow-auto rounded-none border border-border/40 bg-term-bg p-3 font-mono text-[11px] leading-relaxed text-muted-foreground">
                  {JSON.stringify(part, null, 2)}
                </pre>
              </CollapsibleContent>
            </Collapsible>
          );
        }
        return null;
      })}
    </div>
  );
}

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
  const [text, setText] = useState("");
  const [systemNotes, setSystemNotes] = useState<SystemNote[]>([]);
  const [editingLastUser, setEditingLastUser] = useState(false);
  const [editDraft, setEditDraft] = useState("");
  const [cliSettingsOpen, setCliSettingsOpen] = useState(false);
  const [cliSettingsIndex, setCliSettingsIndex] = useState(0);
  const [paletteIndex, setPaletteIndex] = useState(0);
  const [paletteTextKey, setPaletteTextKey] = useState(text);
  if (text !== paletteTextKey) {
    setPaletteTextKey(text);
    setPaletteIndex(0);
  }
  const textareaRef = useRef<HTMLTextAreaElement>(null);
  const editTextareaRef = useRef<HTMLTextAreaElement>(null);
  const scrollRef = useRef<HTMLDivElement>(null);
  const stickToBottomRef = useRef(true);
  const [showJump, setShowJump] = useState(false);
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
    // One-shot client hydrate if SSR started false (localStorage unavailable on server).
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
            // Send whenever the user set one, including for providers whose
            // catalog entry says requiresModel:false. openai is the only such
            // provider, and gating the header on that flag meant an openai user
            // who picked a model had it dropped here — digigraph then answered on
            // *its* default, which on the shipped config is an OpenRouter model
            // billed to the operator (#2490). byok-ping already sends it on the
            // same condition; the send path now matches the path that validated it.
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
        if (
          first &&
          (threadTitle === "New chat" || threadTitle.trim() === "") &&
          onTitleDerived
        ) {
          const t = first.slice(0, 52) + (first.length > 52 ? "…" : "");
          onTitleDerived(threadId, t);
        }
      },
    });
  const { messages, sendMessage, status, stop, error, regenerate, setMessages } = chat;
  const runtime = useAISDKRuntime(chat);

  const busy = status === "streaming" || status === "submitted";
  const isStreaming = status === "streaming";

  useEffect(() => {
    if (!(busy && editingLastUser)) return;
    // Defer out of the synchronous effect body — react-hooks/set-state-in-effect.
    queueMicrotask(() => {
      setEditingLastUser(false);
      setEditDraft("");
    });
  }, [busy, editingLastUser]);

  const updateStickiness = useCallback(() => {
    const el = scrollRef.current;
    if (!el) return;
    const gap = el.scrollHeight - el.scrollTop - el.clientHeight;
    const atBottom = gap < 72;
    stickToBottomRef.current = atBottom;
    setShowJump(!atBottom);
  }, []);

  useEffect(() => {
    const el = scrollRef.current;
    if (!el) return;
    const onScroll = () => updateStickiness();
    el.addEventListener("scroll", onScroll, { passive: true });
    return () => el.removeEventListener("scroll", onScroll);
  }, [updateStickiness]);

  useEffect(() => {
    if (!stickToBottomRef.current) return;
    const el = scrollRef.current;
    if (!el) return;
    el.scrollTo({ top: el.scrollHeight, behavior: status === "streaming" ? "auto" : "smooth" });
  }, [messages, status, systemNotes.length]);

  useLayoutEffect(() => {
    const ta = textareaRef.current;
    if (!ta) return;
    const style = getComputedStyle(ta);
    const lineHeight = parseFloat(style.lineHeight) || 21;
    const padding =
      parseFloat(style.paddingTop) + parseFloat(style.paddingBottom);
    const maxHeight = lineHeight * MAX_INPUT_LINES + padding;
    ta.style.height = "0px";
    const next = Math.min(ta.scrollHeight, maxHeight);
    ta.style.height = `${next}px`;
    ta.style.overflowY = ta.scrollHeight > maxHeight ? "auto" : "hidden";
  }, [text]);

  const pushSystemNote = useCallback((msg: string) => {
    setSystemNotes((prev) => [...prev, { id: crypto.randomUUID(), text: msg }]);
  }, []);

  const onSubmit = useCallback(
    async (e: React.FormEvent, overrideText?: string) => {
      e.preventDefault();
      const t = (overrideText ?? text).trim();
      if (!t) return;

      if (t.startsWith("/")) {
        const [rawName, ...rest] = t.split(/\s+/);
        const name = rawName.toLowerCase();
        const arg = rest.join(" ").trim();
        // #3511: client-only transcript aliases — never POST to the transport.
        // Settled-only while busy: drop the in-flight assistant partial.
        if (name === "/copy" || name === "/export") {
          setText("");
          const settled =
            busy && messages.length > 0 && messages[messages.length - 1]?.role === "assistant"
              ? messages.slice(0, -1)
              : messages;
          const lastSettledAssistant = [...settled]
            .reverse()
            .find((m) => m.role === "assistant" && messagePlainText(m).trim());
          if (name === "/copy") {
            if (!lastSettledAssistant) {
              pushSystemNote("No assistant answer to copy yet.");
              return;
            }
            const plain = messagePlainText(lastSettledAssistant);
            const sources =
              lastSettledAssistant.role === "assistant"
                ? citationHits(messageActivities(lastSettledAssistant)).map((h) => ({
                    title: h.title,
                    path: h.path,
                  }))
                : undefined;
            const markdown = serializeAssistantMarkdown(plain, sources);
            if (!markdown.trim()) {
              pushSystemNote("No assistant answer to copy yet.");
              return;
            }
            const result = await copyMarkdownWithFallback(markdown, {
              filename: "digichat-answer.md",
            });
            pushSystemNote(
              result === "clipboard"
                ? "Copied last answer to clipboard."
                : result === "download"
                  ? "Clipboard blocked — saved last answer as digichat-answer.md."
                  : result === "postMessage"
                    ? "Copied last answer (parent frame)."
                    : "Clipboard blocked — answer selected below, press ⌘C / ctrl+C.",
            );
            return;
          }
          const sub = arg.toLowerCase();
          if (sub && sub !== "last") {
            pushSystemNote("Use /export or /export last.");
            return;
          }
          if (sub === "last") {
            if (!lastSettledAssistant) {
              pushSystemNote("Nothing to export yet.");
              return;
            }
            const plain = messagePlainText(lastSettledAssistant);
            const sources = citationHits(messageActivities(lastSettledAssistant)).map((h) => ({
              title: h.title,
              path: h.path,
            }));
            const md = serializeAssistantMarkdown(plain, sources);
            if (!md.trim()) {
              pushSystemNote("Nothing to export yet.");
              return;
            }
            try {
              downloadMarkdown("digichat-answer.md", md);
              pushSystemNote("Exported last answer as digichat-answer.md.");
            } catch {
              pushSystemNote("Export failed in this browser.");
            }
            return;
          }
          const turns = settled
            .filter((m) => m.role === "user" || m.role === "assistant")
            .map((m) => {
              const content = messagePlainText(m);
              if (m.role === "assistant") {
                return {
                  role: "assistant" as const,
                  content,
                  sources: citationHits(messageActivities(m)).map((h) => ({
                    title: h.title,
                    path: h.path,
                  })),
                };
              }
              return { role: "user" as const, content };
            });
          const md = serializeThreadMarkdown(turns);
          if (!md.trim()) {
            pushSystemNote("Nothing to export yet.");
            return;
          }
          try {
            downloadMarkdown("digichat-thread.md", md);
            pushSystemNote("Exported thread as digichat-thread.md.");
          } catch {
            pushSystemNote("Export failed in this browser.");
          }
          return;
        }
        if (busy) return;
        setText("");
        if (name === "/help") {
          pushSystemNote(
            "available: /help, /clear, /search, /vault, /byok, /websearch, /settings, /model <id>, /history, /scope, /copy, /export, /key",
          );
          return;
        }
        if (name === "/scope") {
          // Full JWT scope surfacing lands with #202 (SSO); this is a no-op visual placeholder.
          pushSystemNote("scope: (signed-in session) — scope surfacing lands with SSO in #202.");
          return;
        }
        if (name === "/model") {
          pushSystemNote("model selector is part of /byok.");
          return;
        }
        if (name === "/websearch") {
          if (!webSearchAllowed) {
            pushSystemNote("Web search is not enabled for this tenant.");
            return;
          }
          const next = !webSearchPref;
          writeWebSearchPref("auth", next);
          setWebSearchPref(next);
          pushSystemNote(`Web search ${next ? "on" : "off"} (External cites).`);
          return;
        }
        if (name === "/settings") {
          setCliSettingsOpen(true);
          setCliSettingsIndex(0);
          return;
        }
        if (name === "/byok" || name === "/key") {
          onByokModeChange?.(true);
          return;
        }
        if (onSlashCommand && onSlashCommand(t)) {
          return;
        }
        const parsed = parseSlashInput(t);
        if (parsed.kind === "command" && parsed.command.forceTool) {
          setPendingForceTool(threadId, parsed.command.forceTool);
          await sendMessage({ text: parsed.arg });
          return;
        }
        pushSystemNote(`Unknown command \`${name}\`. Type /help.`);
        return;
      }

      if (busy) return;
      setText("");
      await sendMessage({ text: t });
    },
    [
      text,
      busy,
      messages,
      sendMessage,
      onSlashCommand,
      onByokModeChange,
      pushSystemNote,
      webSearchAllowed,
      webSearchPref,
      threadId,
    ],
  );

  const onCopyMessage = useCallback(async (m: UIMessage) => {
    const plain = messagePlainText(m);
    const sources =
      m.role === "assistant"
        ? citationHits(messageActivities(m)).map((h) => ({ title: h.title, path: h.path }))
        : undefined;
    const markdown =
      m.role === "assistant" ? serializeAssistantMarkdown(plain, sources) : plain.trim();
    await copyMarkdownWithFallback(markdown, { filename: "digichat-answer.md" });
  }, []);

  const onDownloadThread = useCallback(() => {
    const turns = messages
      .filter((m) => m.role === "user" || m.role === "assistant")
      .map((m) => {
        const content = messagePlainText(m);
        if (m.role === "assistant") {
          return {
            role: "assistant" as const,
            content,
            sources: citationHits(messageActivities(m)).map((h) => ({
              title: h.title,
              path: h.path,
            })),
          };
        }
        return { role: "user" as const, content };
      });
    const md = serializeThreadMarkdown(turns);
    if (!md.trim()) return;
    downloadMarkdown("digichat-thread.md", md);
  }, [messages]);

  const lastAssistant = [...messages].reverse().find((m) => m.role === "assistant");
  let lastUserIndex = -1;
  for (let i = messages.length - 1; i >= 0; i--) {
    if (messages[i]?.role === "user") {
      lastUserIndex = i;
      break;
    }
  }
  const lastUser = lastUserIndex >= 0 ? messages[lastUserIndex] : undefined;
  const canRegenerate = !busy && !!lastAssistant && messages.length > 0 && status === "ready" && !editingLastUser;
  const canEditLastUser = !busy && !!lastUser && status === "ready" && !editingLastUser;
  const canExportThread = !busy && messages.some((m) => messagePlainText(m).trim());

  const beginEditLastUser = useCallback(() => {
    if (!canEditLastUser || !lastUser) return;
    setEditingLastUser(true);
    setEditDraft(messagePlainText(lastUser));
    queueMicrotask(() => editTextareaRef.current?.focus());
  }, [canEditLastUser, lastUser]);

  const cancelEditLastUser = useCallback(() => {
    setEditingLastUser(false);
    setEditDraft("");
  }, []);

  const submitEditLastUser = useCallback(() => {
    const next = editDraft.trim();
    if (!next || lastUserIndex < 0 || busy) return;
    // Shorten the persisted list — ChatShell must pass allowTruncate (#3466).
    onAllowTruncate?.(threadId);
    setMessages(messages.slice(0, lastUserIndex));
    setEditingLastUser(false);
    setEditDraft("");
    setPendingTurnMode(threadId, "edit_last_user");
    void sendMessage({
      role: "user",
      parts: [{ type: "text", text: next }],
    });
  }, [
    editDraft,
    lastUserIndex,
    busy,
    onAllowTruncate,
    threadId,
    setMessages,
    messages,
    sendMessage,
  ]);

  const startsWithSlash = text.trimStart().startsWith("/");
  const slashVisibility = { webSearch: webSearchAllowed, byok: true };
  const sharedSlashMatches = matchingSlashCommands(text, slashVisibility).filter((c) =>
    ["websearch", "byok", "settings", "help", "copy", "export"].includes(c.id),
  );
  const q = text.trim().toLowerCase();
  const extraMatches =
    q.startsWith("/") && !/\s/.test(q)
      ? APP_SLASH_EXTRA.filter((row) => row.cmd.startsWith(q) || q.startsWith(row.cmd))
      : [];
  const paletteRows: Array<{ cmd: string; hint: string; activate: () => void }> = [
    ...sharedSlashMatches.map((cmd) => ({
      cmd: cmd.names[0],
      hint: cmd.hint,
      activate: () => {
        if (
          cmd.id === "websearch" ||
          cmd.id === "byok" ||
          cmd.id === "settings" ||
          cmd.id === "help" ||
          cmd.id === "copy" ||
          cmd.id === "export"
        ) {
          void onSubmit({ preventDefault() {} } as React.FormEvent, cmd.names[0]);
          return;
        }
        setText(cmd.needsArg ? `${cmd.names[0]} ` : cmd.names[0]);
        textareaRef.current?.focus();
      },
    })),
    ...extraMatches.map((row) => ({
      cmd: row.cmd,
      hint: row.hint,
      activate: () => {
        void onSubmit({ preventDefault() {} } as React.FormEvent, row.cmd);
      },
    })),
  ];

  return (
    <AssistantRuntimeProvider runtime={runtime}>
    <ThreadPrimitive.Root className="flex h-full min-h-0 flex-1 flex-col">
      {headerSlot}

      <ThreadPrimitive.Viewport className="relative min-h-0 flex-1" autoScroll={false}>
        <div ref={scrollRef} className="h-full overflow-y-auto rounded-none border border-border/40 dc-term-pane">
          {messages.length === 0 && systemNotes.length === 0 && !byokMode ? (
            <div className="dc-term-row dc-term-row-assistant">
              <span className="dc-term-marker">▸</span>
              <div className="dc-term-body" style={{ color: "var(--text-secondary)" }}>
                digichat ready. Ask a question or type <code className="font-mono">/help</code> for
                commands — <code className="font-mono">/byok</code> anytime for your own key.
              </div>
            </div>
          ) : null}

          {messages.map((m, i) => {
            const isUser = m.role === "user";
            const isLastAssistant = m.role === "assistant" && m.id === lastAssistant?.id;
            const isLastUser = isUser && i === lastUserIndex;
            const showEditForm = isLastUser && editingLastUser;
            return (
              <div
                key={m.id}
                className={cn(
                  "dc-term-row group/message",
                  isUser ? "dc-term-row-user" : "dc-term-row-assistant",
                )}
              >
                <span className="dc-term-marker" aria-hidden>
                  {isUser ? ">" : "▸"}
                </span>
                <div className="dc-term-body">
                  {showEditForm ? (
                    <div className="flex flex-col gap-2">
                      <textarea
                        ref={editTextareaRef}
                        className="min-h-[4.5rem] w-full resize-y rounded-none border border-border/60 bg-transparent p-2 text-sm"
                        value={editDraft}
                        onChange={(e) => setEditDraft(e.target.value)}
                        onKeyDown={(e) => {
                          if (e.key === "Escape") {
                            e.preventDefault();
                            cancelEditLastUser();
                          } else if (e.key === "Enter" && !e.shiftKey) {
                            e.preventDefault();
                            submitEditLastUser();
                          }
                        }}
                        aria-label="Edit last message"
                        maxLength={2000}
                      />
                      <div className="flex flex-wrap items-center gap-1">
                        <Button
                          type="button"
                          variant="ghost"
                          size="sm"
                          className="h-6 text-[11px] text-muted-foreground"
                          disabled={!editDraft.trim()}
                          onClick={submitEditLastUser}
                        >
                          save
                        </Button>
                        <Button
                          type="button"
                          variant="ghost"
                          size="sm"
                          className="h-6 text-[11px] text-muted-foreground"
                          onClick={cancelEditLastUser}
                        >
                          cancel
                        </Button>
                      </div>
                    </div>
                  ) : (
                    <MessageBody
                      message={m}
                      isStreaming={isStreaming && isLastAssistant}
                    />
                  )}
                  {!showEditForm ? (
                    <div
                      className={cn(
                        "mt-2 flex flex-wrap items-center gap-1 opacity-0 transition-opacity group-hover/message:opacity-100",
                        (isLastAssistant || isLastUser) && "opacity-100",
                      )}
                    >
                      <Button
                        type="button"
                        variant="ghost"
                        size="sm"
                        className="h-6 text-[11px] text-muted-foreground"
                        onClick={() => void onCopyMessage(m)}
                      >
                        <Copy className="mr-1 size-3" />
                        copy
                      </Button>
                      {isLastAssistant && canExportThread ? (
                        <Button
                          type="button"
                          variant="ghost"
                          size="sm"
                          className="h-6 text-[11px] text-muted-foreground"
                          onClick={onDownloadThread}
                          aria-label="Download thread as markdown"
                        >
                          md
                        </Button>
                      ) : null}
                      {isLastAssistant ? (
                        <Button
                          type="button"
                          variant="ghost"
                          size="sm"
                          className="h-6 text-[11px] text-muted-foreground"
                          disabled={!canRegenerate}
                          title="Replays the full digigraph workflow on this session"
                          onClick={() => {
                            setPendingTurnMode(threadId, "regenerate");
                            void regenerate();
                          }}
                        >
                          <RefreshCw className="mr-1 size-3" />
                          regen
                        </Button>
                      ) : null}
                      {isLastUser ? (
                        <Button
                          type="button"
                          variant="ghost"
                          size="sm"
                          className="h-6 text-[11px] text-muted-foreground"
                          disabled={!canEditLastUser}
                          title="Replaces this turn and replays the digigraph workflow"
                          onClick={beginEditLastUser}
                        >
                          edit
                        </Button>
                      ) : null}
                    </div>
                  ) : null}
                </div>
              </div>
            );
          })}

          {systemNotes.map((n) => (
            <div key={n.id} className="dc-term-row dc-term-row-assistant">
              <span className="dc-term-marker" aria-hidden>·</span>
              <div className="dc-term-body" style={{ color: "var(--text-secondary)", fontFamily: "var(--font-family-mono)", fontSize: 12 }}>
                {n.text}
              </div>
            </div>
          ))}

          {error ? (
            <div className="dc-term-row dc-term-row-assistant">
              {/* error state rides the four-state system (--down) — a livery is an identity, never a semantic (canon §16) */}
              <span className="dc-term-marker" style={{ color: "var(--down)" }}>✗</span>
              <div className="dc-term-body" style={{ color: "var(--down)" }}>
                {error.message}
              </div>
            </div>
          ) : null}

          {byokMode ? (
            <ByokCliFlow
              onClose={() => onByokModeChange?.(false)}
              onActivate={(key, provider, model) => {
                setByokKey(key, provider, model);
                onByokModeChange?.(false);
              }}
              onClear={clearByokKey}
              active={
                byokIsSet
                  ? { provider: byokProvider, model: byokModel }
                  : null
              }
              initialProvider={byokProvider}
              initialModel={byokModel}
            />
          ) : null}

          {cliSettingsOpen && !byokMode ? (
            <div className="dc-term-row dc-term-row-assistant" role="dialog" aria-label="Settings">
              <span className="dc-term-marker">▸</span>
              <pre className="dc-term-body font-mono text-xs" style={{ color: "var(--text-secondary)" }}>
                {[
                  "settings",
                  webSearchAllowed
                    ? `${cliSettingsIndex === 0 ? ">" : " "} [websearch ${webSearchPref ? "on" : "off"}] Web search — External cites`
                    : null,
                  `${cliSettingsIndex === (webSearchAllowed ? 1 : 0) ? ">" : " "} BYOK → ${byokIsSet ? "update" : "configure"} — /byok`,
                  "",
                  "Up/Down · Enter flip/open · Esc close",
                ]
                  .filter(Boolean)
                  .join("\n")}
              </pre>
            </div>
          ) : null}
        </div>

        {showJump ? (
          <div className="pointer-events-none absolute bottom-4 left-1/2 z-10 -translate-x-1/2">
            <Button
              type="button"
              size="sm"
              variant="secondary"
              className="pointer-events-auto shadow-md"
              onClick={() => {
                const el = scrollRef.current;
                if (!el) return;
                el.scrollTo({ top: el.scrollHeight, behavior: "smooth" });
                stickToBottomRef.current = true;
                setShowJump(false);
              }}
            >
              <ArrowDown className="mr-1 size-4" />
              New messages
            </Button>
          </div>
        ) : null}
      </ThreadPrimitive.Viewport>

      <QuantComparisonStrip messages={messages} conversationId={threadId} />

      {paletteRows.length ? (
        <ul className="dc-slash mb-1 list-none border-b border-border/40 px-2 py-1" role="listbox" aria-label="Slash commands">
          {paletteRows.map((row, i) => (
            <li key={`${row.cmd}-${row.hint}`}>
              <button
                type="button"
                role="option"
                className={cn(
                  "flex w-full gap-3 px-1 py-1 text-left text-xs",
                  i === paletteIndex && "text-[var(--accent)]",
                )}
                aria-selected={i === paletteIndex}
                onMouseEnter={() => setPaletteIndex(i)}
                onClick={() => row.activate()}
              >
                <span className="font-mono min-w-[5.5rem]">{row.cmd}</span>
                <span className="opacity-70">{row.hint}</span>
              </button>
            </li>
          ))}
        </ul>
      ) : null}

      <form onSubmit={onSubmit} className="app-input mt-2">
        <span className={cn("app-input-marker", startsWithSlash && "dc-input-slash-glyph")}>
          {startsWithSlash ? "/" : ">"}
        </span>
        <textarea
          ref={textareaRef}
          value={text}
          onChange={(e) => setText(e.target.value)}
          placeholder="ask digichat"
          className="app-input-field"
          rows={1}
          disabled={busy || byokMode}
          onKeyDown={(e) => {
            if (cliSettingsOpen) {
              const rowCount = webSearchAllowed ? 2 : 1;
              if (e.key === "ArrowDown" || e.key === "ArrowUp") {
                e.preventDefault();
                setCliSettingsIndex((i) =>
                  nextPaletteIndex(i, e.key === "ArrowDown" ? 1 : -1, rowCount),
                );
                return;
              }
              if (e.key === "Enter" && !e.shiftKey) {
                e.preventDefault();
                if (webSearchAllowed && cliSettingsIndex === 0) {
                  void onSubmit(e, "/websearch");
                } else {
                  setCliSettingsOpen(false);
                  onByokModeChange?.(true);
                }
                return;
              }
              if (e.key === "Escape") {
                e.preventDefault();
                setCliSettingsOpen(false);
                return;
              }
            }
            if (paletteRows.length && (e.key === "ArrowDown" || e.key === "ArrowUp")) {
              e.preventDefault();
              setPaletteIndex((i) =>
                nextPaletteIndex(i, e.key === "ArrowDown" ? 1 : -1, paletteRows.length),
              );
              return;
            }
            if (paletteRows.length && e.key === "Enter" && !e.shiftKey) {
              e.preventDefault();
              const row = paletteRows[paletteIndex] ?? paletteRows[0];
              row?.activate();
              return;
            }
            if (e.key === "Enter" && !e.shiftKey) {
              e.preventDefault();
              void onSubmit(e);
            }
          }}
        />
        <span className="slash-hint" aria-hidden>
          {byokIsSet ? (
            <Key className="inline size-3 opacity-80" aria-label="BYOK key set" />
          ) : null}
          {busy ? (
            <button
              type="button"
              onClick={() => stop()}
              className="ml-2 underline-offset-2 hover:underline"
              style={{ background: "transparent", border: "none", color: "inherit", cursor: "pointer", fontFamily: "inherit" }}
            >
              <Square className="inline size-3" /> stop
            </button>
          ) : (
            <kbd>↵</kbd>
          )}
        </span>
      </form>
    </ThreadPrimitive.Root>
    </AssistantRuntimeProvider>
  );
}

/** Kept for back-compat with any external importers. Renders a simple mono strip. */
export function ChatChrome({
  threadTitle,
  userSubtitle,
  leading,
}: {
  threadTitle: string;
  userSubtitle: string;
  leading?: React.ReactNode;
}) {
  return (
    <header className="app-topbar">
      {leading}
      <span className="app-topbar-title">{threadTitle || "digichat"}</span>
      <span className="app-topbar-meta">{userSubtitle}</span>
    </header>
  );
}
