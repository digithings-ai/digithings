"use client";

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
import {
  ArrowDown,
  Copy,
  RefreshCw,
  Send,
  Sparkles,
  Square,
  Wrench,
} from "lucide-react";
import { signOut } from "next-auth/react";
import Link from "next/link";
import { Button } from "@/components/ui/button";
import { Textarea } from "@/components/ui/textarea";
import { Card } from "@/components/ui/card";
import { Separator } from "@/components/ui/separator";
import {
  Collapsible,
  CollapsibleContent,
  CollapsibleTrigger,
} from "@/components/ui/collapsible";
import {
  Tooltip,
  TooltipContent,
  TooltipTrigger,
} from "@/components/ui/tooltip";
import { ConnectionsSheet } from "@/components/connections-sheet";
import { BYOKSettingsPanel } from "@/components/byok-settings-panel";
import { QuantComparisonStrip } from "@/components/quant-comparison-strip";
import { EChartsCard } from "@/components/echarts-card";
import { parseChartEnvelope } from "@/lib/chart-spec";
import type { DigigraphTracePayload } from "@/lib/stream-digigraph-trace";
import { useBYOKKey } from "@/hooks/use-byok-key";
import { cn } from "@/lib/utils";
import { Badge } from "@/components/ui/badge";

/**
 * Custom renderers for ReactMarkdown. The `code` component intercepts fenced
 * JSON code blocks whose payload matches the chart envelope discriminator
 * ({"type":"chart","spec":{...}}) and substitutes an EChartsCard in place of
 * the raw JSON. All other code blocks fall through to the default rendering.
 */
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
  return message.parts
    .filter(isTextUIPart)
    .map((p) => p.text)
    .join("");
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
    <Collapsible className="rounded-lg border border-emerald-950/40 bg-emerald-950/15">
      <CollapsibleTrigger className="flex w-full cursor-pointer items-center gap-2 px-3 py-2 text-left text-xs font-medium uppercase tracking-wide text-emerald-200/90 hover:bg-emerald-950/25">
        Sources
        <Badge variant="secondary" className="text-[10px] font-normal">
          {sources.length}
        </Badge>
      </CollapsibleTrigger>
      <CollapsibleContent className="space-y-2 border-t border-emerald-950/30 px-3 py-2">
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
              className="rounded-md border border-border/35 bg-black/25 px-2 py-1.5 text-[11px] leading-snug text-muted-foreground"
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
      </CollapsibleContent>
    </Collapsible>
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
    <Collapsible className="rounded-lg border border-sky-950/40 bg-sky-950/15">
      <CollapsibleTrigger className="flex w-full cursor-pointer items-center px-3 py-2 text-left text-xs font-medium uppercase tracking-wide text-sky-200/90 hover:bg-sky-950/25">
        Research brief
      </CollapsibleTrigger>
      <CollapsibleContent className="space-y-2 border-t border-sky-950/30 px-3 py-2 text-[11px] text-muted-foreground">
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
            <p className="mb-1 text-[10px] font-semibold uppercase tracking-wide text-sky-200/80">
              Next questions
            </p>
            <ul className="list-inside list-decimal space-y-1">
              {qs.slice(0, 12).map((q, i) => (
                <li key={i}>{q}</li>
              ))}
            </ul>
          </div>
        ) : null}
      </CollapsibleContent>
    </Collapsible>
  );
}

function DigigraphTraceBlock({ data }: { data: DigigraphTracePayload | undefined }) {
  if (!data?.type) return null;
  const payload = data.payload as Record<string, unknown> | undefined;
  if (data.type === "rag_sources" && payload?.sources && Array.isArray(payload.sources)) {
    return <RagSourcesTrace sources={payload.sources} />;
  }
  if (data.type === "graph_update" && payload?.research_brief) {
    return (
      <ResearchBriefTrace
        brief={payload.research_brief}
        questions={payload.profiling_questions}
      />
    );
  }
  const svc =
    typeof data.service === "string" && data.service.trim() ? data.service.trim() : null;
  return (
    <Collapsible className="rounded-lg border border-border/40 bg-muted/20">
      <CollapsibleTrigger className="flex w-full cursor-pointer px-3 py-2 text-left text-xs text-muted-foreground hover:bg-muted/35">
        Trace: {data.type}
        {svc ? (
          <span className="ml-2 rounded bg-background/60 px-1.5 py-0.5 font-mono text-[10px] text-foreground/80">
            {svc}
          </span>
        ) : null}
      </CollapsibleTrigger>
      <CollapsibleContent>
        <pre className="max-h-48 overflow-auto border-t border-border/40 p-2 font-mono text-[10px]">
          {JSON.stringify(data, null, 2)}
        </pre>
      </CollapsibleContent>
    </Collapsible>
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

function MessageBody({ message }: { message: UIMessage }) {
  if (message.role === "user") {
    const text = messagePlainText(message);
    return (
      <div className="prose prose-invert prose-sm max-w-none text-[var(--foreground)]">
        <ReactMarkdown remarkPlugins={[remarkGfm]} components={markdownComponents}>
          {text}
        </ReactMarkdown>
      </div>
    );
  }

  return (
    <div className="space-y-3">
      {message.parts.map((part, i) => {
        if (isReasoningUIPart(part)) {
          return (
            <Collapsible
              key={i}
              className="rounded-lg border border-border/60 bg-muted/30"
            >
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
              className="prose prose-invert prose-sm max-w-none text-[var(--foreground)]"
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
            <Collapsible
              key={i}
              className="overflow-hidden rounded-lg border border-border/50 bg-black/35"
            >
              <CollapsibleTrigger className="flex w-full cursor-pointer items-center gap-2 px-3 py-2 text-left text-xs font-medium text-muted-foreground hover:bg-muted/20">
                <Wrench className="size-3.5 shrink-0 opacity-80" />
                <span className="truncate">{label}</span>
              </CollapsibleTrigger>
              <CollapsibleContent>
                <pre className="max-h-56 overflow-auto border-t border-border/40 p-3 font-mono text-[11px] leading-relaxed text-muted-foreground">
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

export type ChatPanelProps = {
  threadId: string;
  threadTitle: string;
  initialMessages: UIMessage[];
  onMessagesCommit: (threadId: string, messages: UIMessage[]) => void;
  onTitleDerived?: (threadId: string, title: string) => void;
  headerSlot?: React.ReactNode;
};

export function ChatPanel({
  threadId,
  threadTitle,
  initialMessages,
  onMessagesCommit,
  onTitleDerived,
  headerSlot,
}: ChatPanelProps) {
  const [text, setText] = useState("");
  const textareaRef = useRef<HTMLTextAreaElement>(null);
  const scrollRef = useRef<HTMLDivElement>(null);
  const stickToBottomRef = useRef(true);
  const [showJump, setShowJump] = useState(false);
  const { key: byokKey, provider: byokProvider } = useBYOKKey();

  const transport = useMemo(
    () =>
      new DefaultChatTransport<UIMessage>({
        api: "/api/chat",
        credentials: "include",
        prepareSendMessagesRequest: ({ messages, id, body, headers }) => {
          const h = new Headers(headers as HeadersInit | undefined);
          h.set("X-Digichat-Session", threadId);
          if (byokKey) {
            h.set("X-BYOK-Key", byokKey);
            h.set("X-BYOK-Provider", byokProvider);
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
    [threadId, byokKey, byokProvider]
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
    el.scrollTo({
      top: el.scrollHeight,
      behavior: status === "streaming" ? "auto" : "smooth",
    });
  }, [messages, status]);

  useLayoutEffect(() => {
    const ta = textareaRef.current;
    if (!ta) return;
    ta.style.height = "0px";
    ta.style.height = `${Math.min(ta.scrollHeight, 220)}px`;
  }, [text]);

  const onSubmit = useCallback(
    async (e: React.FormEvent) => {
      e.preventDefault();
      const t = text.trim();
      if (!t || busy) return;
      setText("");
      await sendMessage({ text: t });
    },
    [text, busy, sendMessage]
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
  const canRegenerate =
    !busy && !!lastAssistant && messages.length > 0 && status === "ready";

  return (
    <div className="flex h-full min-h-0 flex-1 flex-col">
      {headerSlot}

      <div className="relative min-h-0 flex-1">
        <div
          ref={scrollRef}
          className="h-full overflow-y-auto rounded-xl border border-border/40 bg-card/30"
        >
          <div className="flex flex-col gap-4 p-4">
            {messages.length === 0 && (
              <Card className="border-dashed border-border/50 bg-muted/15 p-6 text-center">
                <Sparkles className="mx-auto mb-3 h-8 w-8 text-primary opacity-90" />
                <p className="text-sm text-muted-foreground">
                  Ask the DigiGraph orchestrator through DigiChat. Messages stream from your
                  stack via the BFF — the browser never calls DigiGraph directly.
                </p>
              </Card>
            )}
            {messages.map((m) => {
              const isUser = m.role === "user";
              const isLastAssistant = m.role === "assistant" && m.id === lastAssistant?.id;
              return (
                <div
                  key={m.id}
                  className={cn(
                    "group/message max-w-[min(100%,40rem)] rounded-2xl border px-4 py-3",
                    isUser
                      ? "ml-auto rounded-br-md border-border/40 bg-secondary/35"
                      : "mr-auto rounded-bl-md border-border/40 bg-background/40 shadow-sm"
                  )}
                >
                  <MessageBody message={m} />
                  <div
                    className={cn(
                      "mt-2 flex flex-wrap items-center gap-1 border-t border-border/30 pt-2 opacity-0 transition-opacity group-hover/message:opacity-100",
                      isLastAssistant && "opacity-100"
                    )}
                  >
                    <Tooltip>
                      <TooltipTrigger
                        render={
                          <Button
                            type="button"
                            variant="ghost"
                            size="sm"
                            className="h-7 text-xs text-muted-foreground"
                            onClick={() => onCopyMessage(m)}
                          >
                            <Copy className="mr-1 size-3.5" />
                            Copy
                          </Button>
                        }
                      />
                      <TooltipContent>Copy message</TooltipContent>
                    </Tooltip>
                    {isLastAssistant ? (
                      <Tooltip>
                        <TooltipTrigger
                          render={
                            <Button
                              type="button"
                              variant="ghost"
                              size="sm"
                              className="h-7 text-xs text-muted-foreground"
                              disabled={!canRegenerate}
                              onClick={() => void regenerate()}
                            >
                              <RefreshCw className="mr-1 size-3.5" />
                              Regenerate
                            </Button>
                          }
                        />
                        <TooltipContent>Regenerate last reply</TooltipContent>
                      </Tooltip>
                    ) : null}
                  </div>
                </div>
              );
            })}
            {error && (
              <Card className="border-destructive/40 bg-destructive/10 p-4 text-sm text-destructive-foreground">
                {error.message}
              </Card>
            )}
          </div>
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

      <Separator className="my-3 bg-border/50" />

      <QuantComparisonStrip messages={messages} conversationId={threadId} />

      <form onSubmit={onSubmit} className="flex shrink-0 flex-col gap-2 sm:flex-row sm:items-end">
        <Textarea
          ref={textareaRef}
          value={text}
          onChange={(e) => setText(e.target.value)}
          placeholder="Research, RAG, backtests…"
          className="min-h-[48px] max-h-[220px] flex-1 resize-none overflow-y-auto bg-background/80"
          rows={1}
          disabled={busy}
          onKeyDown={(e) => {
            if (e.key === "Enter" && !e.shiftKey) {
              e.preventDefault();
              void onSubmit(e);
            }
          }}
        />
        <div className="flex gap-2">
          {busy ? (
            <Button type="button" variant="secondary" onClick={() => stop()}>
              <Square className="mr-2 h-4 w-4" />
              Stop
            </Button>
          ) : null}
          <Button type="submit" disabled={busy || !text.trim()}>
            <Send className="mr-2 h-4 w-4" />
            Send
          </Button>
        </div>
      </form>
    </div>
  );
}

export type ChatChromeProps = {
  threadTitle: string;
  userSubtitle: string;
  leading?: React.ReactNode;
};

/** Top bar: sidebar trigger, branding, ecosystem, links, sign out — used inside ChatShell main column. */
export function ChatChrome({
  threadTitle,
  userSubtitle,
  leading,
}: ChatChromeProps) {
  return (
    <header className="sticky top-0 z-20 flex shrink-0 flex-wrap items-center justify-between gap-3 border-b border-border/50 bg-background/90 py-3 backdrop-blur-sm">
      <div className="flex min-w-0 flex-1 items-center gap-2">
        {leading}
        <h1 className="truncate text-sm font-semibold tracking-tight text-foreground md:text-base">
          {threadTitle || "DigiChat"}
        </h1>
      </div>
      <p className="sr-only">{userSubtitle}</p>
      <nav className="flex flex-wrap items-center gap-1 md:gap-2">
        <BYOKSettingsPanel />
        <ConnectionsSheet />
        <Link
          href="https://digithings.ai"
          target="_blank"
          rel="noreferrer"
          className="rounded-md px-2 py-1 text-xs text-muted-foreground hover:bg-muted hover:text-foreground md:text-sm"
        >
          digithings
        </Link>
        <Button
          type="button"
          variant="ghost"
          size="sm"
          className="text-muted-foreground"
          onClick={() => signOut({ callbackUrl: "/login" })}
        >
          Sign out
        </Button>
      </nav>
    </header>
  );
}
