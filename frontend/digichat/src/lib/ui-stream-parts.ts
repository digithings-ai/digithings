/**
 * 2.0 UI-stream mapping: ActivitySpan → standard AI SDK UI chunks.
 *
 * Generic `useChat` / assistant-ui clients must not need digichat vocabulary.
 * Branded `data-digichatActivity` is not written. The activityDetail gate still
 * runs before this mapper (callers pass an already-gated span).
 */
import type { UIMessage, UIMessageChunk } from "ai";
import type { ActivityDocument, ActivitySpan } from "@/lib/chat-activity";

/** Unbranded conversation-id part (Foundry continuity). Was data-externalConversation. */
export const CONVERSATION_PART_TYPE = "data-conversation" as const;

export type UiStreamWriter = {
  write: (chunk: UIMessageChunk) => void;
};

export type StandardActivityContext = {
  seq: number;
  /** toolName → in-flight toolCallId */
  toolIds: Map<string, string>;
  started: Set<string>;
  inputAvailable: Set<string>;
  reasoningId: string | null;
};

export function createActivityWriteContext(): StandardActivityContext {
  return {
    seq: 0,
    toolIds: new Map(),
    started: new Set(),
    inputAvailable: new Set(),
    reasoningId: null,
  };
}

function nextId(ctx: StandardActivityContext, prefix: string): string {
  ctx.seq += 1;
  return `${prefix}-${ctx.seq}`;
}

function isHttpUrl(path: string): boolean {
  return /^https?:\/\//i.test(path);
}

function toolNameOf(span: ActivitySpan): string {
  const name = span.toolName?.trim();
  return name || "tool";
}

function ensureToolStart(
  writer: UiStreamWriter,
  ctx: StandardActivityContext,
  name: string,
  title?: string,
): string {
  let id = ctx.toolIds.get(name);
  if (!id) {
    id = nextId(ctx, "tool");
    ctx.toolIds.set(name, id);
  }
  if (!ctx.started.has(id)) {
    writer.write({
      type: "tool-input-start",
      toolCallId: id,
      toolName: name,
      ...(title ? { title } : {}),
    });
    ctx.started.add(id);
  }
  return id;
}

function ensureToolInput(
  writer: UiStreamWriter,
  ctx: StandardActivityContext,
  id: string,
  name: string,
  span: ActivitySpan,
): void {
  if (ctx.inputAvailable.has(id)) return;
  writer.write({
    type: "tool-input-available",
    toolCallId: id,
    toolName: name,
    input: { query: span.query ?? "", label: span.label },
  });
  ctx.inputAvailable.add(id);
}

function writeSource(
  writer: UiStreamWriter,
  ctx: StandardActivityContext,
  doc: ActivityDocument,
): void {
  const sourceId = nextId(ctx, "src");
  if (isHttpUrl(doc.path)) {
    writer.write({
      type: "source-url",
      sourceId,
      url: doc.path,
      title: doc.title,
    });
    return;
  }
  writer.write({
    type: "source-document",
    sourceId,
    mediaType: doc.body ? "text/markdown" : "text/plain",
    title: doc.title,
    filename: doc.path,
  });
}

/**
 * Map one gated ActivitySpan onto standard UI message chunks.
 * Does not write `data-digichatActivity`.
 */
export function writeStandardActivity(
  writer: UiStreamWriter,
  span: ActivitySpan,
  ctx: StandardActivityContext,
): void {
  if (span.reasoningDelta) {
    if (!ctx.reasoningId) {
      ctx.reasoningId = nextId(ctx, "reasoning");
      writer.write({ type: "reasoning-start", id: ctx.reasoningId });
    }
    writer.write({
      type: "reasoning-delta",
      id: ctx.reasoningId,
      delta: span.reasoningDelta,
    });
    return;
  }

  if (span.brief) {
    writer.write({
      type: "data-status",
      id: nextId(ctx, "status"),
      data: {
        status: span.status,
        label: span.label,
        brief: span.brief,
      },
    });
    return;
  }

  if (span.operation === "execute_tool") {
    const name = toolNameOf(span);
    const id = ensureToolStart(writer, ctx, name, span.label);
    if (span.status === "started") {
      if (span.query) {
        writer.write({
          type: "tool-input-delta",
          toolCallId: id,
          inputTextDelta: span.query,
        });
      }
      return;
    }
    ensureToolInput(writer, ctx, id, name, span);
    writer.write({
      type: "tool-output-available",
      toolCallId: id,
      output: {
        status: span.status,
        label: span.label,
        query: span.query ?? "",
      },
    });
    return;
  }

  if (span.operation === "retrieve") {
    const name = toolNameOf(span);
    const id = ensureToolStart(writer, ctx, name, span.label);
    ensureToolInput(writer, ctx, id, name, span);
    const docs = span.documents ?? [];
    const withheld = span.documentsWithheld === true;
    writer.write({
      type: "tool-output-available",
      toolCallId: id,
      output: {
        status: span.status,
        label: span.label,
        query: span.query ?? "",
        hitCount: typeof span.hitCount === "number" ? span.hitCount : docs.length,
        documentsWithheld: withheld,
        documents: withheld ? undefined : docs,
      },
    });
    if (!withheld) {
      for (const doc of docs) writeSource(writer, ctx, doc);
    }
    return;
  }

  writer.write({
    type: "data-status",
    id: nextId(ctx, "status"),
    data: { status: span.status, label: span.label },
    transient: span.status === "started",
  });
}

/** Close an open reasoning block at end of stream. */
export function finishStandardActivity(
  writer: UiStreamWriter,
  ctx: StandardActivityContext,
): void {
  if (!ctx.reasoningId) return;
  writer.write({ type: "reasoning-end", id: ctx.reasoningId });
  ctx.reasoningId = null;
}

/**
 * Strip tool / source / data parts before convertToModelMessages.
 * digigraph speaks Chat Completions text, not UI tool parts.
 */
export function uiMessagesForUpstream(messages: UIMessage[]): UIMessage[] {
  return messages
    .filter((m) => m.role === "user" || m.role === "assistant" || m.role === "system")
    .map((m) => ({
      ...m,
      parts: m.parts.filter((p) => p.type === "text"),
    }));
}

export function conversationIdFromParts(
  parts: ReadonlyArray<{ type: string; data?: unknown }>,
): string | undefined {
  for (const part of parts) {
    if (part.type !== CONVERSATION_PART_TYPE && part.type !== "data-externalConversation") {
      continue;
    }
    const id = (part.data as { conversationId?: unknown } | undefined)?.conversationId;
    if (typeof id === "string" && id.trim()) return id.trim();
  }
  return undefined;
}
