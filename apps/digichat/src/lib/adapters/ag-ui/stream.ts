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
import { guardRound, type TurnGuard } from "@/lib/guardrails/turn";
import {
  createTextWriter,
  isRecord,
  iterateSse,
  parseSseJson,
  parseToolInput,
  protocolJsonHeaders,
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
  /** False when this new tool call is past the cap and must not be rendered. */
  admitToolStart?: () => boolean;
};

function consumeEvent(event: Record<string, unknown>, c: Consumer): boolean {
  const type = stringField(event, "type");
  if (!type) return false;

  switch (type) {
    case "THINKING_TEXT_MESSAGE_CONTENT": {
      writeReasoningDelta(c.writer, c.ctx, stringField(event, "delta") ?? "", c.activityDetail);
      return false;
    }
    case "TEXT_MESSAGE_CONTENT": {
      c.text.delta(stringField(event, "delta") ?? "");
      return false;
    }
    case "TOOL_CALL_START": {
      const callId = stringField(event, "toolCallId") ?? "tool";
      const name = stringField(event, "toolCallName") ?? "tool";
      if (c.toolNames.has(callId)) return false;
      if (c.admitToolStart && !c.admitToolStart()) return true;
      c.toolNames.set(callId, name);
      c.text.close();
      writeGatedSpan(
        c.writer,
        c.ctx,
        { operation: "execute_tool", status: "started", label: name, toolName: name, callId },
        c.activityDetail,
      );
      return false;
    }
    case "TOOL_CALL_ARGS": {
      const callId = stringField(event, "toolCallId") ?? "tool";
      const delta = stringField(event, "delta") ?? "";
      if (delta) c.toolArgs.set(callId, (c.toolArgs.get(callId) ?? "") + delta);
      return false;
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
      return false;
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
      return false;
    }
    case "RUN_ERROR": {
      const message = stringField(event, "message") ?? "AG-UI run failed";
      c.text.close();
      writeFailureStatus(c.writer, c.ctx, message, c.activityDetail);
      return false;
    }
    default:
      return false;
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
  guard?: TurnGuard;
}): Promise<Response> {
  const headers = protocolJsonHeaders({
    apiKey: opts.apiKey,
    accept: "text/event-stream",
  });
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
      const upstream = new AbortController();
      const stopVisitor = () => upstream.abort();
      opts.signal?.addEventListener("abort", stopVisitor);
      let toolCallsSoFar = 0;
      let capped = false;
      const admitToolStart = () => {
        const guard = opts.guard;
        if (!guard?.active || guard.toolCap == null) return true;
        if (toolCallsSoFar >= guard.toolCap) {
          guard.noteToolCap(writer, toolCallsSoFar);
          capped = true;
          upstream.abort();
          return false;
        }
        toolCallsSoFar += 1;
        return true;
      };
      try {
        const instruction = await guardRound(opts.guard, {
          writer,
          pendingText: body,
          signal: opts.signal,
        });
        let requestBody = body;
        if (instruction) {
          const parsed = JSON.parse(body) as { messages: { role: string; content: string }[] };
          parsed.messages.push({ role: "user", content: instruction });
          requestBody = JSON.stringify(parsed);
        }
        const res = await fetch(opts.backend.url, {
          method: "POST",
          headers,
          body: requestBody,
          signal: upstream.signal,
        });
        if (!res.ok || !res.body) {
          await res.body?.cancel().catch(() => {});
          const label = `AG-UI ${res.status}`;
          writeFailureStatus(writer, ctx, label, opts.activityDetail);
          // activityDetail "off" drops the status row. Throw so the UI stream
          // still ends on an error part instead of a successful empty turn.
          throw new Error(label);
        }
        try {
          for await (const evt of iterateSse(res.body, upstream.signal)) {
            const json = parseSseJson(evt.data);
            if (!json || !isRecord(json)) continue;
            if (
              consumeEvent(json, {
                writer,
                ctx,
                text,
                activityDetail: opts.activityDetail,
                toolNames,
                toolArgs,
                admitToolStart,
              })
            ) {
              break;
            }
          }
        } catch (err) {
          if (!capped || opts.signal?.aborted) throw err;
        }
      } finally {
        opts.signal?.removeEventListener("abort", stopVisitor);
        opts.guard?.release();
        text.close();
        finishStandardActivity(writer, ctx);
      }
    },
  });

  return createUIMessageStreamResponse({ stream, headers: opts.responseHeaders });
}
