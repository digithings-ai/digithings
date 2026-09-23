/**
 * LangGraph Platform adapter (#4543).
 *
 * Stateless run: `POST {apiUrl}/runs/stream` with `assistant_id` and the chat
 * messages, no thread management. The SSE stream carries `event:
 * messages/partial` frames whose data is an array of message chunks plus
 * `messages/complete` for settled messages.
 *
 * Reasoning rides `additional_kwargs.reasoning_content` (how LangChain
 * surfaces provider thinking) and tool calls ride `tool_call_chunks`
 * (streaming) / `tool_calls` (complete); tool results arrive as ToolMessage
 * frames carrying `tool_call_id`.
 */
import { createUIMessageStream, createUIMessageStreamResponse, type UIMessage } from "ai";
import type { ActivityDetail } from "@/lib/chat-activity";
import {
  createActivityWriteContext,
  finishStandardActivity,
  uiMessagesForUpstream,
  type StandardActivityContext,
  type UiStreamWriter,
} from "@/lib/ui-stream-parts";
import { toChatMessages } from "@/lib/adapters/shared/messages";
import {
  createTextWriter,
  isRecord,
  iterateSse,
  parseSseValue,
  parseToolInput,
  stringField,
  writeGatedSpan,
  writeReasoningDelta,
  type TextWriter,
} from "@/lib/adapters/shared/stream-utils";
import type { LangGraphBackendConfig } from "@/lib/backend-adapters";

type Consumer = {
  writer: UiStreamWriter;
  ctx: StandardActivityContext;
  text: TextWriter;
  activityDetail: ActivityDetail;
  toolNames: Map<string, string>;
};

/** Answer text from a LangChain chunk: a plain string or content blocks. */
function contentText(value: unknown): string {
  if (typeof value === "string") return value;
  if (!Array.isArray(value)) return "";
  let out = "";
  for (const block of value) {
    if (!isRecord(block)) continue;
    if (block.type === "text" && typeof block.text === "string") out += block.text;
  }
  return out;
}

/** Provider thinking on a LangChain chunk (or nested on `additional_kwargs`). */
function contentReasoning(chunk: Record<string, unknown>): string {
  const kwargs = isRecord(chunk.additional_kwargs) ? chunk.additional_kwargs : null;
  const direct = kwargs ? stringField(kwargs, "reasoning_content") : null;
  if (direct) return direct;
  if (!Array.isArray(chunk.content)) return "";
  let out = "";
  for (const block of chunk.content) {
    if (!isRecord(block)) continue;
    if (block.type === "reasoning" && typeof block.reasoning === "string") out += block.reasoning;
  }
  return out;
}

function consumeChunk(chunk: Record<string, unknown>, c: Consumer): void {
  const reasoning = contentReasoning(chunk);
  if (reasoning) writeReasoningDelta(c.writer, c.ctx, reasoning, c.activityDetail);

  const text = contentText(chunk.content);
  if (text) c.text.delta(text);

  // Streaming tool calls: `tool_call_chunks: [{ id, name, args }]`.
  const chunks = Array.isArray(chunk.tool_call_chunks) ? chunk.tool_call_chunks : [];
  for (const raw of chunks) {
    if (!isRecord(raw)) continue;
    const callId = stringField(raw, "id") ?? `tool-${String(raw.index ?? "0")}`;
    const name = stringField(raw, "name");
    if (name) c.toolNames.set(callId, name);
    if (!name || c.ctx.rowByCallId.has(callId)) continue;
    c.text.close();
    writeGatedSpan(
      c.writer,
      c.ctx,
      { operation: "execute_tool", status: "started", label: name, toolName: name, callId },
      c.activityDetail,
    );
  }

  // Settled tool calls: `tool_calls: [{ id, name, args }]`.
  const calls = Array.isArray(chunk.tool_calls) ? chunk.tool_calls : [];
  for (const raw of calls) {
    if (!isRecord(raw)) continue;
    const callId = stringField(raw, "id") ?? "tool";
    const name = stringField(raw, "name") ?? c.toolNames.get(callId) ?? "tool";
    const input = parseToolInput(raw.args);
    c.text.close();
    writeGatedSpan(
      c.writer,
      c.ctx,
      {
        operation: "execute_tool",
        status: "completed",
        label: name,
        toolName: name,
        callId,
        ...(input ? { toolInput: input } : {}),
      },
      c.activityDetail,
    );
  }

  // ToolMessage result: `{ type: "tool", tool_call_id, content }`.
  if (chunk.type === "tool") {
    const callId = stringField(chunk, "tool_call_id") ?? stringField(chunk, "id") ?? "tool";
    const name = c.toolNames.get(callId) ?? stringField(chunk, "name") ?? "tool";
    const result = contentText(chunk.content);
    c.text.close();
    writeGatedSpan(
      c.writer,
      c.ctx,
      {
        operation: "execute_tool",
        status: chunk.status === "error" ? "failed" : "completed",
        label: name,
        toolName: name,
        callId,
        ...(result ? { toolResult: { content: result } } : {}),
      },
      c.activityDetail,
    );
  }
}

export async function createLangGraphStreamResponse(opts: {
  backend: LangGraphBackendConfig;
  messages: UIMessage[];
  responseHeaders: Record<string, string>;
  activityDetail: ActivityDetail;
  /** Resolved by the caller from `backend.apiKeyEnv`; null when unset. */
  apiKey: string | null;
  signal?: AbortSignal;
}): Promise<Response> {
  const url = `${opts.backend.apiUrl.replace(/\/+$/, "")}/runs/stream`;
  const headers: Record<string, string> = {
    "Content-Type": "application/json",
    Accept: "text/event-stream",
  };
  if (opts.apiKey) headers["x-api-key"] = opts.apiKey;
  const body = JSON.stringify({
    assistant_id: opts.backend.assistantId,
    input: { messages: toChatMessages(uiMessagesForUpstream(opts.messages)) },
    stream_mode: ["messages"],
  });

  const stream = createUIMessageStream({
    onError: (error) => (error instanceof Error ? error.message : "langgraph stream error"),
    execute: async ({ writer }) => {
      const ctx = createActivityWriteContext();
      const text = createTextWriter(writer, ctx);
      const toolNames = new Map<string, string>();
      try {
        const res = await fetch(url, {
          method: "POST",
          headers,
          body,
          signal: opts.signal,
        });
        if (!res.ok || !res.body) {
          writer.write({
            type: "data-status",
            id: "langgraph-error",
            data: { status: "failed", label: `LangGraph ${res.status}` },
          });
          return;
        }
        for await (const evt of iterateSse(res.body, opts.signal)) {
          // LangGraph `messages/*` frames carry an ARRAY of message chunks.
          const value = parseSseValue(evt.data);
          if (value === null) continue;
          const frames = Array.isArray(value) ? value : [value];
          for (const frame of frames) {
            if (isRecord(frame)) consumeChunk(frame, { writer, ctx, text, activityDetail: opts.activityDetail, toolNames });
          }
        }
      } finally {
        text.close();
        finishStandardActivity(writer, ctx);
      }
    },
  });

  return createUIMessageStreamResponse({ stream, headers: opts.responseHeaders });
}
