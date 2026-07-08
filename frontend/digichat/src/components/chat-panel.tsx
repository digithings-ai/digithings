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
  DefaultChatTransport,
  isReasoningUIPart,
  isTextUIPart,
  type UIMessage,
} from "ai";
import ReactMarkdown from "react-markdown";
import remarkGfm from "remark-gfm";
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
import type { DigigraphTracePayload } from "@/lib/stream-digigraph-trace";
import { useBYOKKey } from "@/hooks/use-byok-key";
import { cn } from "@/lib/utils";
import { Badge } from "@/components/ui/badge";

const MAX_INPUT_LINES = 5;

const markdownComponents = {
  code(props: {
    className?: string;
    children?: React.ReactNode;
    inline?: boolean;
    node?: unknown;
  }) {
    const { className, children, inline } = props;
    const text = Array.isArray(children)
      ? children.join("")
      : typeof children === "string"
        ? children
        : "";
    const isFenced = !inline && /language-json/i.test(className ?? "");
    if (isFenced) {
      const spec = parseChartEnvelope(text);
      if (spec) {
        return <EChartsCard spec={spec} />;
      }
    }
    return <code className={className}>{children}</code>;
  },
};

function messagePlainText(message: UIMessage): string {
  if (!message.parts?.length) return "";
  return message.parts.filter(isTextUIPart).map((p) => p.text).join("");
}

function isDigigraphTracePart(part: unknown): part is { type: "data-digigraphTrace"; data: DigigraphTracePayload } {
  return (
    !!part &&
    typeof part === "object" &&
    "type" in part &&
    (part as { type: string }).type === "data-digigraphTrace"
  );
}

function tierLabel(metadata: Record<string, unknown>): string | null {
  const t = metadata.evidence_tier ?? metadata["evidence_tier"];
  if (typeof t === "string" && t.trim()) return t;
  const pr = metadata.peer_reviewed;
  if (pr === true) return "peer_reviewed";
  return null;
}

function RagSourcesTrace({ sources }: { sources: unknown[] }) {
  if (!sources.length) return null;
  return (
    <details className="dc-sources">
      <summary>sources · {sources.length}</summary>
      <div className="space-y-2 border-t border-border/30 px-3 py-2">
        {sources.map((raw, idx) => {
          const s = raw as Record<string, unknown>;
          const meta = (s.metadata as Record<string, unknown>) || {};
          const tier = tierLabel(meta);
          const title = (meta.title as string) || (meta.doi_or_arxiv as string) || "";
          const sid = (s.source_id as string) || (s.doc_id as string) || `#${idx + 1}`;
          const year = meta.publication_year;
          return (
            <div
              key={`${sid}-${idx}`}
              className="rounded-md border border-border/35 bg-term-bg px-2 py-1.5 text-[11px] leading-snug text-muted-foreground"
            >
              <div className="flex flex-wrap items-center gap-1.5">
                <span className="font-mono text-[10px] text-foreground/90">{sid}</span>
                {tier ? (
                  <Badge variant="outline" className="text-[9px] font-normal">
                    {tier}
                  </Badge>
                ) : null}
                {typeof year === "number" ? (
                  <span className="text-[10px] opacity-80">{year}</span>
                ) : null}
              </div>
              {title ? <p className="mt-1 text-foreground/80">{title}</p> : null}
              {typeof s.snippet === "string" && s.snippet ? (
                <p className="mt-1 line-clamp-4 opacity-90">{s.snippet}</p>
              ) : null}
            </div>
          );
        })}
      </div>
    </details>
  );
}

function ResearchBriefTrace({
  brief,
  questions,
}: {
  brief: unknown;
  questions: unknown;
}) {
  if (!brief || typeof brief !== "object") return null;
  const b = brief as Record<string, unknown>;
  const themes = b.themes as Array<Record<string, unknown>> | undefined;
  const qs = Array.isArray(questions) ? (questions as string[]) : [];
  return (
    <details className="dc-sources">
      <summary>research brief</summary>
      <div className="space-y-2 border-t border-border/30 px-3 py-2 text-[11px] text-muted-foreground">
        {themes?.length ? (
          <ul className="list-inside list-disc space-y-1">
            {themes.slice(0, 8).map((t, i) => (
              <li key={i}>
                <span className="font-medium text-foreground/85">{String(t.label || "")}</span>
                {t.summary ? ` — ${String(t.summary).slice(0, 220)}` : ""}
              </li>
            ))}
          </ul>
        ) : null}
        {qs.length ? (
          <div>
            <p className="mb-1 text-[10px] font-semibold uppercase tracking-wide">
              Next questions
            </p>
            <ul className="list-inside list-decimal space-y-1">
              {qs.slice(0, 12).map((q, i) => (
                <li key={i}>{q}</li>
              ))}
            </ul>
          </div>
        ) : null}
      </div>
    </details>
  );
}

function DigigraphTraceBlock({ data }: { data: DigigraphTracePayload | undefined }) {
  if (!data?.type) return null;
  const payload = data.payload as Record<string, unknown> | undefined;
  if (data.type === "rag_sources" && payload?.sources && Array.isArray(payload.sources)) {
    return <RagSourcesTrace sources={payload.sources} />;
  }
  if (data.type === "graph_update" && payload?.research_brief) {
    return <ResearchBriefTrace brief={payload.research_brief} questions={payload.profiling_questions} />;
  }
  const svc = typeof data.service === "string" && data.service.trim() ? data.service.trim() : null;
  return (
    <details className="dc-sources">
      <summary>
        trace: {data.type}
        {svc ? <span className="ml-2 font-mono text-[10px]">{svc}</span> : null}
      </summary>
      <pre className="max-h-48 overflow-auto border-t border-border/40 p-2 font-mono text-[10px]">
        {JSON.stringify(data, null, 2)}
      </pre>
    </details>
  );
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
      <div className="prose prose-invert prose-sm max-w-none text-[var(--text-primary)]">
        <ReactMarkdown remarkPlugins={[remarkGfm]} components={markdownComponents}>
          {text}
        </ReactMarkdown>
      </div>
    );
  }

  return (
    <div className="space-y-3">
      {message.parts.map((part, i) => {
        const isLast = i === message.parts.length - 1;
        if (isReasoningUIPart(part)) {
          return (
            <Collapsible key={i} className="rounded-lg border border-border/60 bg-muted/30">
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
            <div
              key={i}
              className={cn(
                "prose prose-invert prose-sm max-w-none text-[var(--text-primary)]",
                isLast && isStreaming && "dc-term-streaming",
              )}
            >
              <ReactMarkdown remarkPlugins={[remarkGfm]} components={markdownComponents}>
                {part.text}
              </ReactMarkdown>
            </div>
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
                <pre className="mt-2 max-h-56 overflow-auto rounded-md border border-border/40 bg-term-bg p-3 font-mono text-[11px] leading-relaxed text-muted-foreground">
                  {JSON.stringify(part, null, 2)}
                </pre>
              </CollapsibleContent>
            </Collapsible>
          );
        }
        if (isDigigraphTracePart(part)) {
          return <DigigraphTraceBlock key={i} data={part.data} />;
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
  headerSlot,
  byokMode = false,
  onByokModeChange,
  onSlashCommand,
}: ChatPanelProps) {
  const [text, setText] = useState("");
  const [systemNotes, setSystemNotes] = useState<SystemNote[]>([]);
  const textareaRef = useRef<HTMLTextAreaElement>(null);
  const scrollRef = useRef<HTMLDivElement>(null);
  const stickToBottomRef = useRef(true);
  const [showJump, setShowJump] = useState(false);
  const { key: byokKey, provider: byokProvider, model: byokModel, isSet: byokIsSet } = useBYOKKey();

  const transport = useMemo(
    () =>
      new DefaultChatTransport<UIMessage>({
        api: p("/api/chat"),
        credentials: "include",
        prepareSendMessagesRequest: ({ messages, id, body, headers }) => {
          const h = new Headers(headers as HeadersInit | undefined);
          h.set("X-Digichat-Session", threadId);
          if (byokKey) {
            h.set("X-BYOK-Key", byokKey);
            h.set("X-BYOK-Provider", byokProvider);
            if (byokProvider === "openrouter" && byokModel.trim()) {
              h.set("X-BYOK-Model", byokModel.trim());
            }
          }
          return {
            body: { ...(typeof body === "object" && body !== null ? body : {}), id, messages },
            headers: h,
          };
        },
      }),
    [threadId, byokKey, byokProvider, byokModel],
  );

  const { messages, sendMessage, status, stop, error, regenerate } =
    useChat<UIMessage>({
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

  const busy = status === "streaming" || status === "submitted";
  const isStreaming = status === "streaming";

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
    async (e: React.FormEvent) => {
      e.preventDefault();
      const t = text.trim();
      if (!t || busy) return;

      if (t.startsWith("/")) {
        setText("");
        const [name] = t.split(/\s+/);
        if (name === "/help") {
          pushSystemNote(
            "available: /help, /clear, /key, /model <id>, /history, /settings, /scope",
          );
          return;
        }
        if (name === "/scope") {
          // Full JWT scope surfacing lands with #202 (SSO); this is a no-op visual placeholder.
          pushSystemNote("scope: (signed-in session) — scope surfacing lands with SSO in #202.");
          return;
        }
        if (name === "/model") {
          pushSystemNote("model selector is part of /key.");
          return;
        }
        if (name === "/key" || name === "/settings") {
          onByokModeChange?.(true);
          return;
        }
        if (onSlashCommand && onSlashCommand(t)) {
          return;
        }
        pushSystemNote(`Unknown command \`${name}\`. Type /help.`);
        return;
      }

      setText("");
      await sendMessage({ text: t });
    },
    [text, busy, sendMessage, onSlashCommand, onByokModeChange, pushSystemNote],
  );

  const onCopyMessage = useCallback(async (m: UIMessage) => {
    const plain = messagePlainText(m);
    try {
      await navigator.clipboard.writeText(plain);
    } catch {
      /* ignore */
    }
  }, []);

  const lastAssistant = [...messages].reverse().find((m) => m.role === "assistant");
  const canRegenerate = !busy && !!lastAssistant && messages.length > 0 && status === "ready";

  const startsWithSlash = text.trimStart().startsWith("/");

  if (byokMode) {
    return (
      <div className="flex h-full min-h-0 flex-1 flex-col">
        {headerSlot}
        <ByokCliFlow onClose={() => onByokModeChange?.(false)} />
      </div>
    );
  }

  return (
    <div className="flex h-full min-h-0 flex-1 flex-col">
      {headerSlot}

      <div className="relative min-h-0 flex-1">
        <div ref={scrollRef} className="h-full overflow-y-auto rounded-md border border-border/40 dc-term-pane">
          {messages.length === 0 && systemNotes.length === 0 ? (
            <div className="dc-term-row dc-term-row-assistant">
              <span className="dc-term-marker">▸</span>
              <div className="dc-term-body" style={{ color: "var(--text-secondary)" }}>
                DigiChat ready. Ask a question or type <code className="font-mono">/help</code> for commands.
              </div>
            </div>
          ) : null}

          {messages.map((m) => {
            const isUser = m.role === "user";
            const isLastAssistant = m.role === "assistant" && m.id === lastAssistant?.id;
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
                  <MessageBody
                    message={m}
                    isStreaming={isStreaming && isLastAssistant}
                  />
                  <div
                    className={cn(
                      "mt-2 flex flex-wrap items-center gap-1 opacity-0 transition-opacity group-hover/message:opacity-100",
                      isLastAssistant && !isUser && "opacity-100",
                    )}
                  >
                    <Button
                      type="button"
                      variant="ghost"
                      size="sm"
                      className="h-6 text-[11px] text-muted-foreground"
                      onClick={() => onCopyMessage(m)}
                    >
                      <Copy className="mr-1 size-3" />
                      copy
                    </Button>
                    {isLastAssistant ? (
                      <Button
                        type="button"
                        variant="ghost"
                        size="sm"
                        className="h-6 text-[11px] text-muted-foreground"
                        disabled={!canRegenerate}
                        onClick={() => void regenerate()}
                      >
                        <RefreshCw className="mr-1 size-3" />
                        regen
                      </Button>
                    ) : null}
                  </div>
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
      </div>

      <QuantComparisonStrip messages={messages} conversationId={threadId} />

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
          disabled={busy}
          onKeyDown={(e) => {
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
    </div>
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
      <span className="app-topbar-title">{threadTitle || "DigiChat"}</span>
      <span className="app-topbar-meta">{userSubtitle}</span>
    </header>
  );
}
