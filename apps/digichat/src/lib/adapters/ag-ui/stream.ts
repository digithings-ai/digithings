/**
 * AG-UI adapter (#4543).
 *
 * `POST {url}` with `{ threadId, runId, messages, tools }` and an
 * `Accept: text/event-stream` response. Each SSE frame is a JSON event with a
 * `type` discriminator; the ones that carry chat content are the text,
 * thinking and tool-call families plus `RUN_ERROR`.
 *
 * Thinking is native (`THINKING_TEXT_MESSAGE_CONTENT`), so AG-UI surfaces
 * reasoning the same way digigraph and Foundry do.
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
  parseSseJson,
  parseToolInput,
  stringField,
  writeFailureStatus,
  writeGatedSpan,
  writeReasoningDelta,
  type TextWriter,
} from "@/lib/adapters/shared/stream-utils";
import type { AgUiBackendConfig } from "@/lib/backend-adapters";

type Consumer = {
  writer: UiStreamWriter;
  ctx: StandardActivityContext;
  text: TextWriter;
  activityDetail: ActivityDetail;
  toolNames: Map<string, string>;
  toolArgs: Map<string, string>;
};

function consumeEvent(event: Record<string, unknown>, c: Consumer): void {
  const type = stringField(event, "type");
  if (!type) return;

  switch (type) {
    case "THINKING_TEXT_MESSAGE_CONTENT": {
      writeReasoningDelta(c.writer, c.ctx, stringField(event, "delta") ?? "", c.activityDetail);
      return;
    }
    case "TEXT_MESSAGE_CONTENT": {
      c.text.delta(stringField(event, "delta") ?? "");
      return;
    }
    case "TOOL_CALL_START": {
      const callId = stringField(event, "toolCallId") ?? "tool";
      const name = stringField(event, "toolCallName") ?? "tool";
      c.toolNames.set(callId, name);
      c.text.close();
      writeGatedSpan(
        c.writer,
        c.ctx,
        { operation: "execute_tool", status: "started", label: name, toolName: name, callId },
        c.activityDetail,
      );
      return;
    }
    case "TOOL_CALL_ARGS": {
      const callId = stringField(event, "toolCallId") ?? "tool";
      const delta = stringField(event, "delta") ?? "";
      if (delta) c.toolArgs.set(callId, (c.toolArgs.get(callId) ?? "") + delta);
      return;
    }
    case "TOOL_CALL_END": {
      // Close the row so a server that never sends a result cannot leave the
      // thinking animation parked (finishStandardActivity would settle it as
      // failed; an explicit completion is the truthful terminal state).
      const callId = stringField(event, "toolCallId") ?? "tool";
      const name = c.toolNames.get(callId) ?? "tool";
      const input = parseToolInput(c.toolArgs.get(callId));
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
      return;
    }
    case "TOOL_CALL_RESULT": {
      const callId = stringField(event, "toolCallId") ?? "tool";
      const name = c.toolNames.get(callId) ?? "tool";
      const content = stringField(event, "content");
      const input = parseToolInput(c.toolArgs.get(callId));
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
          ...(content ? { toolResult: { content } } : {}),
        },
        c.activityDetail,
      );
      return;
    }
    case "RUN_ERROR": {
      const message = stringField(event, "message") ?? "AG-UI run failed";
      c.text.close();
      writeFailureStatus(c.writer, c.ctx, message, c.activityDetail);
      return;
    }
    default:
      return;
  }
}

export async function createAgUiStreamResponse(opts: {
  backend: AgUiBackendConfig;
  messages: UIMessage[];
  responseHeaders: Record<string, string>;
  activityDetail: ActivityDetail;
  /** Resolved by the caller from `backend.apiKeyEnv`; null when unset. */
  apiKey: string | null;
  signal?: AbortSignal;
}): Promise<Response> {
  const headers: Record<string, string> = {
    "Content-Type": "application/json",
    Accept: "text/event-stream",
  };
  if (opts.apiKey) headers.Authorization = `Bearer ${opts.apiKey}`;
  const runId = crypto.randomUUID();
  const body = JSON.stringify({
    threadId: runId,
    runId,
    state: {},
    tools: [],
    messages: toChatMessages(uiMessagesForUpstream(opts.messages)),
  });

  const stream = createUIMessageStream({
    onError: (error) => (error instanceof Error ? error.message : "ag-ui stream error"),
    execute: async ({ writer }) => {
      const ctx = createActivityWriteContext();
      const text = createTextWriter(writer, ctx);
      const toolNames = new Map<string, string>();
      const toolArgs = new Map<string, string>();
      try {
        const res = await fetch(opts.backend.url, {
          method: "POST",
          headers,
          body,
          signal: opts.signal,
        });
        if (!res.ok || !res.body) {
          await res.body?.cancel().catch(() => {});
          writeFailureStatus(writer, ctx, `AG-UI ${res.status}`, opts.activityDetail);
          return;
        }
        for await (const evt of iterateSse(res.body, opts.signal)) {
          const json = parseSseJson(evt.data);
          if (!json) continue;
          if (isRecord(json)) {
            consumeEvent(json, { writer, ctx, text, activityDetail: opts.activityDetail, toolNames, toolArgs });
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
