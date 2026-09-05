"use client";

/**
 * assistant-ui MessagePrimitive.Parts component map — CLI-skinned.
 * Product renderer is these parts, not ChatActivities.
 */
import type {
  DataMessagePartProps,
  ReasoningMessagePartProps,
  SourceMessagePartProps,
  TextMessagePartProps,
  ToolCallMessagePartProps,
} from "@assistant-ui/react";
import { isReasoningUIPart, isTextUIPart, type UIMessage } from "ai";
import { ChatMarkdown, ChatThinking, ChatToolCall, type CodeBlockOverride } from "@digithings/web";
import { EChartsCard } from "@/components/echarts-card";
import { parseChartEnvelope } from "@/lib/chart-spec";
import { cn } from "@/lib/utils";

/**
 * digichat-specific fence: ```json chart envelope → live ECharts.
 */
export const renderChartCodeBlock: CodeBlockOverride = (lang, code) => {
  if (lang !== "json") return undefined;
  const spec = parseChartEnvelope(code);
  return spec ? <EChartsCard spec={spec} /> : undefined;
};

export function CliTextPart({ text, status }: TextMessagePartProps) {
  const streaming = status?.type === "running";
  return (
    <ChatMarkdown
      source={text}
      renderCodeBlock={renderChartCodeBlock}
      className={cn("text-[var(--text-primary)]", streaming && "dc-term-streaming")}
    />
  );
}

export function CliReasoningPart({ text, status }: ReasoningMessagePartProps) {
  const live = status?.type === "running";
  return (
    <ChatThinking label="Reasoning" live={live} defaultOpen={live}>
      <pre className="max-h-64 overflow-auto whitespace-pre-wrap font-mono text-xs leading-relaxed text-muted-foreground">
        {text}
      </pre>
    </ChatThinking>
  );
}

export function CliSourcePart(props: SourceMessagePartProps) {
  const title =
    props.title?.trim() ||
    (props.sourceType === "url" ? props.url : props.filename) ||
    "source";
  const path = props.sourceType === "url" ? props.url : (props.filename ?? "");
  return (
    <div className="font-mono text-[11px] leading-relaxed text-muted-foreground">
      <span className="text-[var(--text-primary)]">{title}</span>
      {path && path !== title ? <span className="opacity-70"> — {path}</span> : null}
    </div>
  );
}

type ToolOutput = {
  status?: string;
  label?: string;
  query?: string;
  hitCount?: number;
  documentsWithheld?: boolean;
  documents?: Array<{ title?: string; path?: string }>;
};

export function CliToolFallback({
  toolName,
  args,
  result,
  status,
  isError,
}: ToolCallMessagePartProps) {
  const running = status?.type === "running";
  const output = (result && typeof result === "object" ? result : {}) as ToolOutput;
  const input = (args && typeof args === "object" ? args : {}) as { query?: string; label?: string };
  const label = output.label || input.label || toolName;
  const query = output.query || input.query || "";
  const toolStatus = isError || output.status === "failed" ? "error" : running ? "running" : "ok";
  const hitCount =
    typeof output.hitCount === "number"
      ? output.hitCount
      : Array.isArray(output.documents)
        ? output.documents.length
        : undefined;
  const detail =
    hitCount !== undefined
      ? output.documentsWithheld
        ? `${hitCount} result${hitCount === 1 ? "" : "s"} (detail withheld)`
        : `${hitCount} hit${hitCount === 1 ? "" : "s"}`
      : query
        ? `query: ${query}`
        : null;

  return (
    <ChatToolCall name={label} status={toolStatus}>
      {detail ? (
        <div className="mt-1 font-mono text-[11px] text-muted-foreground">{detail}</div>
      ) : null}
      {Array.isArray(output.documents) && output.documents.length > 0 ? (
        <ul className="mt-1 list-none space-y-0.5 font-mono text-[11px] text-muted-foreground">
          {output.documents.slice(0, 8).map((doc, i) => (
            <li key={`${doc.path ?? doc.title ?? i}`}>
              {doc.title ?? doc.path ?? "document"}
              {doc.path && doc.path !== doc.title ? (
                <span className="opacity-70"> — {doc.path}</span>
              ) : null}
            </li>
          ))}
        </ul>
      ) : null}
    </ChatToolCall>
  );
}

type StatusData = {
  status?: string;
  label?: string;
  brief?: {
    themes?: Array<{ label: string; summary: string }>;
    questions?: string[];
  };
};

export function CliStatusDataPart({ data }: DataMessagePartProps) {
  const d = (data && typeof data === "object" ? data : {}) as StatusData;
  if (d.brief?.themes?.length) {
    return (
      <div className="space-y-2 rounded-none border border-border/40 p-3 font-mono text-xs">
        <div className="text-[var(--text-secondary)]">{d.label || "brief"}</div>
        <ul className="list-none space-y-1">
          {d.brief.themes.map((t) => (
            <li key={t.label}>
              <span className="text-[var(--text-primary)]">{t.label}</span>
              {t.summary ? <span className="opacity-70"> — {t.summary}</span> : null}
            </li>
          ))}
        </ul>
        {d.brief.questions?.length ? (
          <ul className="list-none space-y-0.5 text-muted-foreground">
            {d.brief.questions.map((q) => (
              <li key={q}>? {q}</li>
            ))}
          </ul>
        ) : null}
      </div>
    );
  }
  if (!d.label) return null;
  const done = d.status !== "started";
  return (
    <div className="font-mono text-[11px] text-muted-foreground">
      {done ? "·" : "…"} {d.label}
    </div>
  );
}

/** Ignore Foundry continuity parts in the transcript. */
export function CliConversationDataPart(): null {
  return null;
}

export const cliMessagePartComponents = {
  Text: CliTextPart,
  Reasoning: CliReasoningPart,
  Source: CliSourcePart,
  tools: {
    Fallback: CliToolFallback,
  },
  data: {
    by_name: {
      status: CliStatusDataPart,
      conversation: CliConversationDataPart,
    },
    Fallback: () => null,
  },
};

/**
 * Map an AI SDK UIMessage onto the same part components MessagePrimitive.Parts
 * would use. Primary path for CliThread (uiMessage comes from useAISDKChat).
 */
export function UiMessageParts({
  message,
  isStreaming,
}: {
  message: UIMessage;
  isStreaming?: boolean;
}) {
  const parts = message.parts ?? [];
  return (
    <div className="space-y-3">
      {parts.map((part, i) => {
        const isLast = i === parts.length - 1;
        const running = Boolean(isStreaming && isLast);
        const status = running
          ? ({ type: "running" } as const)
          : ({ type: "complete" } as const);

        if (isTextUIPart(part)) {
          return <CliTextPart key={i} type="text" text={part.text} status={status} />;
        }
        if (isReasoningUIPart(part)) {
          return (
            <CliReasoningPart key={i} type="reasoning" text={part.text} status={status} />
          );
        }
        if (part.type === "source-url") {
          return (
            <CliSourcePart
              key={i}
              type="source"
              sourceType="url"
              id={"sourceId" in part ? String(part.sourceId) : `src-${i}`}
              url={part.url}
              title={part.title}
              status={status}
            />
          );
        }
        if (part.type === "source-document") {
          return (
            <CliSourcePart
              key={i}
              type="source"
              sourceType="document"
              id={"sourceId" in part ? String(part.sourceId) : `src-${i}`}
              title={part.title}
              mediaType={part.mediaType}
              filename={"filename" in part ? part.filename : undefined}
              status={status}
            />
          );
        }
        if (part.type === "data-status") {
          return (
            <CliStatusDataPart
              key={i}
              type="data-status"
              name="status"
              data={"data" in part ? part.data : undefined}
              status={status}
            />
          );
        }
        if (part.type === "data-conversation") {
          return <CliConversationDataPart key={i} />;
        }
        if (
          part.type === "dynamic-tool" ||
          (typeof part.type === "string" && part.type.startsWith("tool-"))
        ) {
          const toolName =
            part.type === "dynamic-tool"
              ? "toolName" in part && typeof part.toolName === "string"
                ? part.toolName
                : "tool"
              : part.type.slice("tool-".length) || "tool";
          const state = "state" in part ? String(part.state) : "";
          const toolStatus =
            state === "output-error" || state === "output-denied"
              ? ({ type: "incomplete", reason: "error" as const } as const)
              : state === "output-available" || state === "result"
                ? ({ type: "complete" } as const)
                : running || state.includes("input") || state === "call" || state === "partial-call"
                  ? ({ type: "running" } as const)
                  : ({ type: "complete" } as const);
          return (
            <CliToolFallback
              key={i}
              type="tool-call"
              toolCallId={"toolCallId" in part ? String(part.toolCallId) : `tool-${i}`}
              toolName={toolName}
              args={"input" in part ? part.input : {}}
              argsText=""
              result={"output" in part ? part.output : undefined}
              isError={state === "output-error"}
              status={toolStatus}
              addResult={() => undefined}
              resume={() => undefined}
              respondToApproval={async () => undefined}
            />
          );
        }
        return null;
      })}
    </div>
  );
}
