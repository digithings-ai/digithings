/**
 * 2.0 UI-stream mapping: ActivitySpan → standard AI SDK UI chunks.
 *
 * Generic `useChat` / assistant-ui clients stream without branded part types.
 * Product payloads (retrieve documents, brief) still need a mapper or tool UI.
 * Branded `data-digichatActivity` is not written. The activityDetail gate still
 * runs before this mapper (callers pass an already-gated span).
 */
import type { UIMessage, UIMessageChunk } from "ai";
import type { ActivityDocument, ActivitySpan } from "@/lib/chat-activity";
import { expandPageContextFileParts } from "@/lib/embed-page-context-messages";

/** Unbranded conversation-id part (Foundry continuity). Was data-externalConversation. */
export const CONVERSATION_PART_TYPE = "data-conversation" as const;

export type UiStreamWriter = {
  write: (chunk: UIMessageChunk) => void;
};

export type StandardActivityContext = {
  seq: number;
  /** In-flight toolCallIds queued per tool name (FIFO — one row per call). */
  pendingByName: Map<string, string[]>;
  /** Last known MCP args keyed by toolCallId (used when retrieve omits them). */
  inputById: Map<string, Record<string, unknown>>;
  started: Set<string>;
  inputAvailable: Set<string>;
  jsonInputWritten: Set<string>;
  reasoningId: string | null;
};

export function createActivityWriteContext(): StandardActivityContext {
  return {
    seq: 0,
    pendingByName: new Map(),
    inputById: new Map(),
    started: new Set(),
    inputAvailable: new Set(),
    jsonInputWritten: new Set(),
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

function toolInputOf(span: ActivitySpan): Record<string, unknown> {
  const input: Record<string, unknown> = { ...(span.toolInput ?? {}) };
  if (span.query && input.query === undefined) input.query = span.query;
  return input;
}

function rememberInput(
  ctx: StandardActivityContext,
  id: string,
  span: ActivitySpan,
): Record<string, unknown> {
  const merged = { ...(ctx.inputById.get(id) ?? {}), ...toolInputOf(span) };
  if (Object.keys(merged).length) ctx.inputById.set(id, merged);
  return merged;
}

function writeToolStart(
  writer: UiStreamWriter,
  ctx: StandardActivityContext,
  name: string,
  title?: string,
): string {
  const id = nextId(ctx, "tool");
  writer.write({
    type: "tool-input-start",
    toolCallId: id,
    toolName: name,
    ...(title ? { title } : {}),
  });
  ctx.started.add(id);
  return id;
}

function beginToolCall(
  writer: UiStreamWriter,
  ctx: StandardActivityContext,
  name: string,
  title?: string,
): string {
  const id = writeToolStart(writer, ctx, name, title);
  let q = ctx.pendingByName.get(name);
  if (!q) {
    q = [];
    ctx.pendingByName.set(name, q);
  }
  q.push(id);
  return id;
}

function completeToolCall(
  writer: UiStreamWriter,
  ctx: StandardActivityContext,
  name: string,
  title?: string,
): string {
  const q = ctx.pendingByName.get(name);
  if (q && q.length) return q.shift() as string;
  return writeToolStart(writer, ctx, name, title);
}

function writeJsonInputDelta(
  writer: UiStreamWriter,
  ctx: StandardActivityContext,
  id: string,
  span: ActivitySpan,
): void {
  if (ctx.jsonInputWritten.has(id)) return;
  const input = rememberInput(ctx, id, span);
  if (!Object.keys(input).length) return;
  writer.write({
    type: "tool-input-delta",
    toolCallId: id,
    inputTextDelta: JSON.stringify(input),
  });
  ctx.jsonInputWritten.add(id);
}

function ensureToolInput(
  writer: UiStreamWriter,
  ctx: StandardActivityContext,
  id: string,
  name: string,
  span: ActivitySpan,
): void {
  if (ctx.inputAvailable.has(id)) return;
  writeJsonInputDelta(writer, ctx, id, span);
  writer.write({
    type: "tool-input-available",
    toolCallId: id,
    toolName: name,
    input: rememberInput(ctx, id, span),
  });
  ctx.inputAvailable.add(id);
}

function writeToolOutput(
  writer: UiStreamWriter,
  ctx: StandardActivityContext,
  id: string,
  span: ActivitySpan,
  extra: Record<string, unknown> = {},
): void {
  const output: Record<string, unknown> = {
    ...rememberInput(ctx, id, span),
    ...extra,
  };
  if (span.status === "failed") output.status = "failed";
  writer.write({
    type: "tool-output-available",
    toolCallId: id,
    output,
  });
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
    if (span.status === "started") {
      const id = beginToolCall(writer, ctx, name, span.label);
      writeJsonInputDelta(writer, ctx, id, span);
      rememberInput(ctx, id, span);
      return;
    }
    const id = completeToolCall(writer, ctx, name, span.label);
    ensureToolInput(writer, ctx, id, name, span);
    writeToolOutput(writer, ctx, id, span);
    return;
  }

  if (span.operation === "retrieve") {
    const name = toolNameOf(span);
    const id = completeToolCall(writer, ctx, name, span.label);
    ensureToolInput(writer, ctx, id, name, span);
    const docs = span.documents ?? [];
    const withheld = span.documentsWithheld === true;
    const hitCount = typeof span.hitCount === "number" ? span.hitCount : docs.length;
    const extra: Record<string, unknown> = { hitCount };
    if (withheld) extra.documentsWithheld = true;
    else if (docs.length) extra.documents = docs;
    writeToolOutput(writer, ctx, id, span, extra);
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

/** Close an open reasoning block and auto-complete leftover read-tool rows. */
export function finishStandardActivity(
  writer: UiStreamWriter,
  ctx: StandardActivityContext,
): void {
  if (ctx.reasoningId) {
    writer.write({ type: "reasoning-end", id: ctx.reasoningId });
    ctx.reasoningId = null;
  }
  for (const [name, queue] of ctx.pendingByName) {
    while (queue.length) {
      const id = queue.shift() as string;
      const stored = ctx.inputById.get(id) ?? {};
      const span: ActivitySpan = {
        operation: "execute_tool",
        status: "completed",
        label: name,
        toolName: name,
        ...(Object.keys(stored).length ? { toolInput: stored } : {}),
      };
      ensureToolInput(writer, ctx, id, name, span);
      writeToolOutput(writer, ctx, id, span);
    }
  }
}

/**
 * Strip tool / source / data parts before convertToModelMessages.
 * digigraph speaks Chat Completions text, not UI tool parts.
 * Page-context document chips are folded into that text first so the model
 * still sees the host snapshot (#3590 preview stays gone).
 */
export function uiMessagesForUpstream(messages: UIMessage[]): UIMessage[] {
  return expandPageContextFileParts(messages)
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
