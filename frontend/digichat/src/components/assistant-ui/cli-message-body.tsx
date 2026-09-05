"use client";

/**
 * Legacy 1.4 branded-part hydrate for old first-party threads.
 * Live turns render through MessagePrimitive.Parts (cli-message-parts).
 */
import type { UIMessage } from "ai";
import { isReasoningUIPart, isTextUIPart } from "ai";
import { ChatThinking, ChatToolCall } from "@digithings/web";
import { ACTIVITY_PART_TYPE, messageActivities } from "@/lib/chat-activity";

export function messagePlainText(message: UIMessage): string {
  if (!message.parts?.length) return "";
  return message.parts.filter(isTextUIPart).map((p) => p.text).join("");
}

function hasStandardActivityParts(message: UIMessage): boolean {
  return (message.parts ?? []).some((part) => {
    if (!part || typeof part !== "object" || !("type" in part)) return false;
    const t = part.type;
    return (
      t === "reasoning" ||
      t === "source-url" ||
      t === "source-document" ||
      t === "data-status" ||
      t === "tool-invocation" ||
      t === "dynamic-tool" ||
      (typeof t === "string" && t.startsWith("tool-"))
    );
  });
}

function hasBrandedActivity(message: UIMessage): boolean {
  return (message.parts ?? []).some(
    (part) => part && typeof part === "object" && "type" in part && part.type === ACTIVITY_PART_TYPE,
  );
}

/** True when this message still needs the 1.4 activity hydrate path. */
export function needsLegacyActivityHydrate(message: UIMessage): boolean {
  return hasBrandedActivity(message) && !hasStandardActivityParts(message);
}

/**
 * Render 1.4 `data-digichatActivity` rows without ChatActivities.
 * Skip when standard parts already cover the turn (MessagePrimitive.Parts).
 */
export function LegacyActivityHydrate({
  message,
  isStreaming,
}: {
  message: UIMessage;
  isStreaming?: boolean;
}) {
  if (!needsLegacyActivityHydrate(message)) return null;
  const activities = messageActivities(message, { settle: !isStreaming });
  if (!activities.length) return null;
  return (
    <div className="space-y-2">
      {activities.map((a, i) => {
        if (a.kind === "reasoning") {
          return (
            <ChatThinking key={i} label="Reasoning" live={false} defaultOpen={false}>
              <pre className="max-h-64 overflow-auto whitespace-pre-wrap font-mono text-xs leading-relaxed text-muted-foreground">
                {a.text}
              </pre>
            </ChatThinking>
          );
        }
        if (a.kind === "tool_call") {
          return (
            <ChatToolCall key={i} name={a.name} status="running">
              {a.query ? (
                <div className="mt-1 font-mono text-[11px] text-muted-foreground">
                  query: {a.query}
                </div>
              ) : null}
            </ChatToolCall>
          );
        }
        if (a.kind === "tool_result") {
          return (
            <ChatToolCall key={i} name={a.name} status="ok">
              <div className="mt-1 font-mono text-[11px] text-muted-foreground">
                {a.count} hit{a.count === 1 ? "" : "s"}
                {a.query ? ` for "${a.query}"` : ""}
              </div>
            </ChatToolCall>
          );
        }
        if (a.kind === "trace") {
          return (
            <div key={i} className="font-mono text-[11px] text-muted-foreground">
              {a.done ? "·" : "…"} {a.label}
            </div>
          );
        }
        if (a.kind === "status") {
          return (
            <div key={i} className="font-mono text-[11px] text-muted-foreground">
              · {a.message}
            </div>
          );
        }
        if (a.kind === "brief") {
          return (
            <div key={i} className="space-y-1 rounded-none border border-border/40 p-2 font-mono text-xs">
              {a.themes.map((t) => (
                <div key={t.label}>
                  <span className="text-[var(--text-primary)]">{t.label}</span>
                  {t.summary ? <span className="opacity-70"> — {t.summary}</span> : null}
                </div>
              ))}
            </div>
          );
        }
        return null;
      })}
    </div>
  );
}

/** @deprecated Prefer MessagePrimitive.Parts + LegacyActivityHydrate. */
export function CliMessageBody({
  message,
  isStreaming,
}: {
  message: UIMessage;
  isStreaming?: boolean;
}) {
  if (message.role === "user") {
    const text = messagePlainText(message);
    return <div data-testid="md">{text}</div>;
  }
  // Tests that still mount CliMessageBody alone see legacy hydrate + plain text.
  const text = messagePlainText(message);
  const reasoning = (message.parts ?? []).filter(isReasoningUIPart);
  return (
    <div className="space-y-3">
      <LegacyActivityHydrate message={message} isStreaming={isStreaming} />
      {reasoning.map((part, i) => (
        <ChatThinking key={i} label="Reasoning" live={false} defaultOpen={false}>
          <pre className="max-h-64 overflow-auto whitespace-pre-wrap font-mono text-xs leading-relaxed text-muted-foreground">
            {part.text}
          </pre>
        </ChatThinking>
      ))}
      {text ? <div data-testid="md">{text}</div> : null}
    </div>
  );
}
