"use client";

import { isReasoningUIPart, isTextUIPart, type UIMessage } from "ai";
import { ChatActivities } from "@digithings/digichat-ui";
import { ChatMarkdown, ChatThinking, ChatToolCall, type CodeBlockOverride } from "@digithings/web";
import { EChartsCard } from "@/components/echarts-card";
import { parseChartEnvelope } from "@/lib/chart-spec";
import { ACTIVITY_PART_TYPE, messageActivities } from "@/lib/chat-activity";
import { cn } from "@/lib/utils";

export function messagePlainText(message: UIMessage): string {
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

/**
 * The one digichat-specific fence shape the shared ChatMarkdown renderer has
 * no reason to know about: a ```json block whose content parses as a chart
 * envelope renders as a live chart.
 */
export const renderChartCodeBlock: CodeBlockOverride = (lang, code) => {
  if (lang !== "json") return undefined;
  const spec = parseChartEnvelope(code);
  return spec ? <EChartsCard spec={spec} /> : undefined;
};

export function CliMessageBody({
  message,
  isStreaming,
}: {
  message: UIMessage;
  isStreaming?: boolean;
}) {
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

  const activities = messageActivities(message, { settle: !isStreaming });
  return (
    <div className="space-y-3">
      {activities.length ? <ChatActivities activities={activities} /> : null}
      {message.parts.map((part, i) => {
        const isLast = i === message.parts.length - 1;
        if (part.type === ACTIVITY_PART_TYPE || part.type === "data-digigraphTrace") return null;
        if (isReasoningUIPart(part)) {
          const reasoningLive = isStreaming && isLast;
          return (
            <ChatThinking
              key={i}
              label="Reasoning"
              live={reasoningLive}
              defaultOpen={reasoningLive}
            >
              <pre className="max-h-64 overflow-auto whitespace-pre-wrap font-mono text-xs leading-relaxed text-muted-foreground">
                {part.text}
              </pre>
            </ChatThinking>
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
          const runState = "state" in part ? (part as { state?: string }).state : undefined;
          const status =
            runState === "output-error" || runState === "output-denied"
              ? "error"
              : runState === "output-available"
                ? "ok"
                : "running";
          return (
            <ChatToolCall key={i} name={label} status={status}>
              <pre className="mt-2 max-h-56 overflow-auto rounded-none border border-border/40 bg-term-bg p-3 font-mono text-[11px] leading-relaxed text-muted-foreground">
                {JSON.stringify(part, null, 2)}
              </pre>
            </ChatToolCall>
          );
        }
        return null;
      })}
    </div>
  );
}
