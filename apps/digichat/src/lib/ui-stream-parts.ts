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
import { toolRowTitle } from "@digithings/ui/chat/stock";

/** Unbranded conversation-id part (Foundry continuity). Was data-externalConversation. */
export const CONVERSATION_PART_TYPE = "data-conversation" as const;

/** Error text on a tool row whose call started but never returned a result. */
export const ABANDONED_TOOL_ERROR = "Tool did not return a result before the stream ended.";

/**
 * MCP meta tools (284.3). Each one decides for itself what to call next, so a
 * consent box naming one asks a human to approve a call nobody has named yet.
 *
 * digigraph already refuses these before they are offered (`MetaToolConfirmationRefused`),
 * so the guard below is unreachable in production — it exists so the *render path*
 * cannot be later reused for a meta tool without a test failing. The leaf brief
 * makes this explicit; CTO bar item 10 calls it moot once 284.3 holds, which is a
 * statement about the server, not about this file.
 */
export const MCP_META_TOOLS = [
  "discover",
  "executeRead",
  "executeWrite",
  "executeDestructive",
] as const;

const META_TOOL_SET: ReadonlySet<string> = new Set(
  MCP_META_TOOLS.map((t) => t.toLowerCase())
);

/**
 * May this tool name be presented as an approvable human decision?
 *
 * Case-insensitive on purpose: the names come from an operator allowlist that is
 * matched case-sensitively upstream, so a differently-cased spelling must not
 * quietly produce an *approvable* card here.
 */
export function isApprovableMcpTool(tool: string | undefined | null): boolean {
  const name = (tool ?? "").trim().toLowerCase();
  if (!name) return false;
  return !META_TOOL_SET.has(name);
}

/** The lean public event digigraph records for a pending human decision (registry.PendingMcpCall.as_public_event). */
export type PendingMcpDecision = {
  pendingId: string;
  serverId: string;
  tool: string;
  /** Argument *names* only. digigraph never sends values here: "Values may be client data." */
  targetArguments: string[];
  message?: string;
};

function str(v: unknown): string {
  return typeof v === "string" ? v.trim() : "";
}

/**
 * Read a pending decision off the digigraph event, or null when the event is not
 * one. digichat decides nothing here: every field is copied from what digigraph
 * reported. There is no branch that classifies a tool as mutating.
 */
export function pendingMcpDecisionFromEvent(
  payload: Record<string, unknown> | undefined
): PendingMcpDecision | null {
  const p = payload ?? {};
  const pendingId = str(p.pending_id);
  const tool = str(p.tool);
  if (!pendingId || !tool) return null;
  const targets = Array.isArray(p.target_arguments)
    ? p.target_arguments.filter((t): t is string => typeof t === "string" && !!t.trim())
    : [];
  return {
    pendingId,
    serverId: str(p.server_id),
    tool,
    targetArguments: targets,
    ...(str(p.message) ? { message: str(p.message) } : {}),
  };
}

/**
 * CTO bar item 10: the confirmation must name the concrete operation and its
 * target, or it tells the human nothing they can consent to. `tool` is the
 * *remote* tool digigraph resolved (`addOrEditJiraIssueComment`, not
 * `executeWrite`), and the target is the argument names digigraph reported.
 */
export function describePendingMcpOperation(decision: PendingMcpDecision): string {
  const where = decision.serverId ? ` on ${decision.serverId}` : "";
  const target = decision.targetArguments.length
    ? ` — target: ${decision.targetArguments.join(", ")}`
    : "";
  return `${decision.tool}${where}${target}`;
}

export type UiStreamWriter = {
  write: (chunk: UIMessageChunk) => void;
};

export type StandardActivityContext = {
  seq: number;
  /**
   * toolCallIds held open awaiting a human decision, mapped to their pending id.
   * Optional so callers that build a context literal elsewhere keep compiling;
   * created on first approval.
   */
  approvalsByToolCallId?: Map<string, string>;
  /** In-flight toolCallIds queued per tool name (FIFO — one row per call). */
  pendingByName: Map<string, string[]>;
  /** Last known MCP args keyed by toolCallId (used when retrieve omits them). */
  inputById: Map<string, Record<string, unknown>>;
  started: Set<string>;
  inputAvailable: Set<string>;
  jsonInputWritten: Set<string>;
  reasoningId: string | null;
  /** BFF wall clock when each tool-input-start was written. */
  startedAt: Map<string, number>;
  /**
   * Provider call correlation (Foundry `call_id`) to open toolCallId. A
   * completion carrying the same call id settles that exact row instead of
   * the name-FIFO head — e.g. a search `_call_output` lands on the row its
   * `_call` opened rather than minting an arg-less second row.
   */
  rowByCallId: Map<string, string>;
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
    startedAt: new Map(),
    rowByCallId: new Map(),
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

function displayTitle(name: string): string {
  return toolRowTitle(name);
}

/** Close the current reasoning part so the next burst mints a new id. */
export function closeOpenReasoning(
  writer: UiStreamWriter,
  ctx: StandardActivityContext,
): void {
  if (!ctx.reasoningId) return;
  writer.write({ type: "reasoning-end", id: ctx.reasoningId });
  ctx.reasoningId = null;
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
  ctx.startedAt.set(id, Date.now());
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
  callId?: string,
): string {
  if (callId) {
    const rowId = ctx.rowByCallId.get(callId);
    if (rowId) {
      // Retain the mapping: Foundry streams a call's OUTPUT as a later item
      // that carries the same call_id (e.g. an `azure_ai_search_call_output`
      // after the search_call's own completion). Re-resolving the same row
      // lets that output update the row in place instead of opening a second
      // one. The map lives for a single response stream.
      const q = ctx.pendingByName.get(name);
      if (q) {
        const at = q.indexOf(rowId);
        if (at !== -1) q.splice(at, 1);
      }
      return rowId;
    }
  }
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
    inputTextDelta: JSON.stringify(input, null, 2),
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

function failedToolErrorText(span: ActivitySpan): string {
  const result = span.toolResult;
  if (typeof result === "string" && result.trim()) return result;
  if (result && typeof result === "object" && !Array.isArray(result)) {
    const record = result as Record<string, unknown>;
    if (typeof record.content === "string" && record.content.trim()) return record.content;
    if (typeof record.error === "string" && record.error.trim()) return record.error;
  }
  return "Tool failed.";
}

function writeToolOutput(
  writer: UiStreamWriter,
  ctx: StandardActivityContext,
  id: string,
  span: ActivitySpan,
  extra: Record<string, unknown> = {},
): void {
  // `tool-output-available` renders as success even when output.status is
  // "failed". assistant-ui flips the row only on `tool-output-error`.
  if (span.status === "failed") {
    writer.write({
      type: "tool-output-error",
      toolCallId: id,
      errorText: failedToolErrorText(span),
    });
    return;
  }
  const output: Record<string, unknown> = {
    ...rememberInput(ctx, id, span),
    ...extra,
  };
  // Generic tool result (e.g. MCP payload): the row's Result pane renders
  // this as JSON, and its arrival is what flips the row to completed.
  if (span.toolResult !== undefined) output.result = span.toolResult;
  const started = ctx.startedAt.get(id);
  if (started !== undefined) {
    output.durationMs = Math.max(0, Date.now() - started);
  }
  writer.write({
    type: "tool-output-available",
    toolCallId: id,
    output,
  });
}

/**
 * Render a pending human decision as an approvable tool row.
 *
 * Emitting `tool-approval-request` is what switches assistant-ui's existing
 * `requires-action` renderer on (useAISDKRuntime.js:87, useExternalHistory.js:27)
 * — the Approve/Deny affordance already exists in
 * `packages/ui/.../tool-fallback.aui.tsx` and has simply never been switched on.
 *
 * Returns the toolCallId, or null when the tool is a meta tool, in which case no
 * approvable confirmation is emitted at all (CTO bar item 10).
 */
export function writePendingMcpApproval(
  writer: UiStreamWriter,
  ctx: StandardActivityContext,
  decision: PendingMcpDecision
): string | null {
  if (!isApprovableMcpTool(decision.tool)) return null;
  const title = describePendingMcpOperation(decision);
  const id = beginToolCall(writer, ctx, decision.tool, title);
  const toolInput: Record<string, unknown> = {
    pending_id: decision.pendingId,
    server_id: decision.serverId,
    target_arguments: decision.targetArguments,
  };
  const span: ActivitySpan = {
    operation: "execute_tool",
    status: "started",
    label: title,
    toolName: decision.tool,
    toolInput,
  };
  rememberInput(ctx, id, span);
  ctx.inputById.set(id, toolInput);
  writer.write({
    type: "tool-approval-request",
    approvalId: decision.pendingId,
    toolCallId: id,
    reason: "tool-calls",
  });
  if (!ctx.approvalsByToolCallId) ctx.approvalsByToolCallId = new Map();
  ctx.approvalsByToolCallId.set(id, decision.pendingId);
  return id;
}

/**
 * Settle a row whose result never arrived. `tool-output-error` is what flips
 * the AI SDK / assistant-ui tool part to an error state; a
 * `tool-output-available` with no result would render it as a success.
 */
function writeAbandonedTool(writer: UiStreamWriter, id: string): void {
  writer.write({
    type: "tool-output-error",
    toolCallId: id,
    errorText: ABANDONED_TOOL_ERROR,
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

  // Tools / status / answer-adjacent spans end this reasoning phase. The next
  // reasoningDelta mints a new id so assistant-ui cannot append round 2 into
  // the first thinking block (same class of bug as reusing one toolCallId).
  closeOpenReasoning(writer, ctx);

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
      const id = beginToolCall(writer, ctx, name, displayTitle(name));
      if (span.callId) ctx.rowByCallId.set(span.callId, id);
      writeJsonInputDelta(writer, ctx, id, span);
      rememberInput(ctx, id, span);
      return;
    }
    const id = completeToolCall(writer, ctx, name, displayTitle(name), span.callId);
    ensureToolInput(writer, ctx, id, name, span);
    writeToolOutput(writer, ctx, id, span);
    return;
  }

  if (span.operation === "retrieve") {
    const name = toolNameOf(span);
    const id = completeToolCall(writer, ctx, name, displayTitle(name), span.callId);
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

/**
 * Close an open reasoning block and settle leftover tool rows. A row still
 * open at stream end never returned a result — its completion trace never
 * arrived — so it is settled as an error, not a success. Most `execute_tool`
 * rows complete mid-stream via their result span; only genuine orphans reach
 * this backstop (which exists so an Approve/Deny affordance cannot stick).
 * Auto-completing them as `completed` renders a lie: a success row whose tool
 * never returned.
 *
 * EXCEPTION — a row held open by `writePendingMcpApproval`. Its result cannot
 * arrive in this stream: the turn was *suspended* (plan §2 D2 — LangGraph's
 * `interrupt_after` drops the resume value, so the decision travels on
 * `POST /api/chat/approve` instead). Settling it as `failed` here would flip the
 * row to an error state and destroy the Approve/Deny affordance, which is the one
 * case where "the result never arrived" means "waiting for a human", not "lost".
 */
export function finishStandardActivity(
  writer: UiStreamWriter,
  ctx: StandardActivityContext,
): void {
  closeOpenReasoning(writer, ctx);
  const held = ctx.approvalsByToolCallId;
  for (const [name, queue] of ctx.pendingByName) {
    while (queue.length) {
      const id = queue.shift() as string;
      if (held?.has(id)) continue;
      const stored = ctx.inputById.get(id) ?? {};
      const span: ActivitySpan = {
        operation: "execute_tool",
        status: "failed",
        label: name,
        toolName: name,
        ...(Object.keys(stored).length ? { toolInput: stored } : {}),
      };
      ensureToolInput(writer, ctx, id, name, span);
      writeAbandonedTool(writer, id);
    }
  }
}

/**
 * Strip tool / source / data parts before convertToModelMessages.
 * digigraph speaks Chat Completions text, not UI tool parts.
 * Page-context document chips are folded into that text first so the model
 * still sees the host snapshot (#3590 preview stays gone).
 *
 * Approval parts are tool parts, so they are stripped here too — deliberately.
 * Brief fact 1 says this function stops the browser returning anything about a
 * tool to digigraph, and the fix is narrow by design: the *decision* does NOT
 * travel through here. It travels on `POST /api/chat/approve`, a separate request
 * for the same session, so no tool name and no argument can be smuggled upstream
 * by forwarding message parts (brief fact 2 and 3).
 */
const UPSTREAM_STRIPPED_PART_TYPES: ReadonlySet<string> = new Set([
  "tool-approval-request",
  "tool-approval-response",
]);

export function uiMessagesForUpstream(messages: UIMessage[]): UIMessage[] {
  return expandPageContextFileParts(messages)
    .filter((m) => m.role === "user" || m.role === "assistant" || m.role === "system")
    .map((m) => ({
      ...m,
      parts: m.parts.filter(
        (p) => p.type === "text" && !UPSTREAM_STRIPPED_PART_TYPES.has(p.type as string)
      ),
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
