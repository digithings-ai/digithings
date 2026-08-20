import {
  convertToModelMessages,
  createUIMessageStream,
  createUIMessageStreamResponse,
  type UIMessage,
} from "ai";
import {
  digigraphChatCompletionsUrl,
  digigraphModelName,
} from "@/lib/digigraph";
import { stripToolDumpFromAnswerDelta } from "@/lib/adapters/digithings/strip-tool-dump";
import { coreMessagesToDigigraphOpenAi } from "@/lib/digigraph-messages";
import {
  ACTIVITY_PART_TYPE,
  type ActivityDetail,
} from "@/lib/chat-activity";
import { mapDigigraphTraceToSpans } from "@/lib/adapters/digithings/activity";

export type DigigraphTracePayload = {
  v?: number;
  type: string;
  /** Originating vertical or hub: digigraph | digisearch | digiquant */
  service?: string;
  payload?: Record<string, unknown>;
  workflow_id?: string;
  request_id?: string;
  session_id?: string;
};

/** Typed digichat contract from digigraph SSE `delta.digigraph_error`. */
export type DigigraphErrorPayload = {
  code?: string;
  message?: string;
};

/** Map digigraph's `{ code, message }` to embed-chat-error's `{ error, message }`. */
export function digigraphErrorToEmbedPayload(err: DigigraphErrorPayload): string {
  const code = typeof err.code === "string" && err.code.length ? err.code : "digigraph_error";
  const payload: { error: string; message?: string } = { error: code };
  if (typeof err.message === "string" && err.message.length) {
    payload.message = err.message;
  }
  return JSON.stringify(payload);
}

/**
 * Parse digigraph's HTTP `ApiErrorEnvelope` (`{"error":{"code","message",...}}`).
 *
 * Used when chat-completions refuses before SSE starts (BYOK middleware 400s). In-stream
 * refusals arrive as `delta.digigraph_error` and never pass through here.
 */
export function parseDigigraphHttpErrorBody(body: string): DigigraphErrorPayload | null {
  const trimmed = body.trim();
  if (!trimmed) return null;
  try {
    const parsed = JSON.parse(trimmed) as {
      error?: { code?: unknown; message?: unknown } | string;
    };
    const err = parsed?.error;
    if (!err || typeof err !== "object") return null;
    const code = err.code;
    if (typeof code !== "string" || !code.length) return null;
    const message = err.message;
    return {
      code,
      message: typeof message === "string" && message.length ? message : undefined,
    };
  } catch {
    return null;
  }
}

class DigigraphStreamContractError extends Error {
  constructor(payload: string) {
    super(payload);
    this.name = "DigigraphStreamContractError";
  }
}

async function* iterateOpenAiSse(
  body: ReadableStream<Uint8Array>
): AsyncGenerator<Record<string, unknown>> {
  const reader = body.getReader();
  const decoder = new TextDecoder();
  let buf = "";
  while (true) {
    const { done, value } = await reader.read();
    if (done) break;
    buf += decoder.decode(value, { stream: true });
    let idx: number;
    while ((idx = buf.indexOf("\n\n")) !== -1) {
      const block = buf.slice(0, idx);
      buf = buf.slice(idx + 2);
      for (const line of block.split("\n")) {
        if (!line.startsWith("data: ")) continue;
        const raw = line.slice(6).trim();
        if (raw === "[DONE]") continue;
        try {
          const json = JSON.parse(raw) as {
            choices?: Array<{ delta?: Record<string, unknown> }>;
          };
          const delta = json.choices?.[0]?.delta;
          if (delta && Object.keys(delta).length) yield delta;
        } catch {
          /* skip malformed chunk */
        }
      }
    }
  }
}

export async function createDigigraphTraceStreamResponse(opts: {
  messages: UIMessage[];
  digigraphBaseUrl: string;
  upstreamHeaders: Record<string, string>;
  responseHeaders: Record<string, string>;
  upstreamBearer: string;
  activityDetail: ActivityDetail;
}) {
  const stripped = opts.messages.map((m) => {
    const { id: _omit, ...rest } = m;
    void _omit;
    return rest;
  }) as Omit<UIMessage, "id">[];
  const coreMessages = await convertToModelMessages(stripped);
  const url = digigraphChatCompletionsUrl(opts.digigraphBaseUrl);
  const model = digigraphModelName();
  const apiKey = opts.upstreamBearer;

  const stream = createUIMessageStream({
    onError: (error) => (error instanceof Error ? error.message : "digigraph stream error"),
    execute: async ({ writer }) => {
      let textSeq = 0;
      let textId = "assistant-main";
      writer.write({ type: "text-start", id: textId });
      let activitySeq = 0;
      const bodyPayload: Record<string, unknown> = {
        model,
        messages: coreMessagesToDigigraphOpenAi(coreMessages),
        stream: true,
      };
      const res = await fetch(url, {
        method: "POST",
        headers: {
          "Content-Type": "application/json",
          Authorization: `Bearer ${apiKey}`,
          ...opts.upstreamHeaders,
          // After upstreamHeaders so dogfood never inherits Open WebUI format.
          // Belt-and-suspenders: digigraph's Open WebUI chrome is opt-in only
          // (X-Response-Format: openwebui or openwebui_format=true), never implied
          // by model id, but dogfood forces plain explicitly rather than relying
          // on that default.
          "X-Suppress-Tool-Stream": "1",
          "X-Response-Format": "plain",
        },
        body: JSON.stringify(bodyPayload),
      });
      if (!res.ok) {
        // Log the upstream detail server-side; never stream a raw 5xx body. A 500
        // can carry stack traces, internal hostnames, and prompt echoes, and this
        // response goes to anonymous embed visitors.
        const detail = (await res.text().catch(() => "")).trim();
        console.error(
          `[digigraph] upstream ${res.status} ${res.statusText}`,
          detail.length > 1500 ? `${detail.slice(0, 1500)}…` : detail
        );
        // Client-remediable digigraph refusals (BYOK model required / default
        // provider mismatch, free_quota_exceeded, …) are HTTP 4xx envelopes that
        // land *before* SSE. Masking them as a soft "unavailable" assistant turn
        // hides the code from embed-chat-error, so the BYOK sequence never
        // reopens (#2490 / #2503). Same contract path as in-stream digigraph_error.
        if (res.status >= 400 && res.status < 500) {
          const parsed = parseDigigraphHttpErrorBody(detail);
          if (parsed) {
            writer.write({ type: "text-end", id: textId });
            throw new DigigraphStreamContractError(digigraphErrorToEmbedPayload(parsed));
          }
        }
        writer.write({
          type: "text-delta",
          id: textId,
          delta: "The assistant is unavailable right now. Please try again shortly.",
        });
        writer.write({ type: "text-end", id: textId });
        return;
      }
      if (!res.body) {
        console.error(`[digigraph] upstream ${res.status} returned an empty body`);
        writer.write({
          type: "text-delta",
          id: textId,
          delta: "The assistant is unavailable right now. Please try again shortly.",
        });
        writer.write({ type: "text-end", id: textId });
        return;
      }
      for await (const delta of iterateOpenAiSse(res.body)) {
        const dgErr = delta.digigraph_error;
        if (dgErr && typeof dgErr === "object") {
          writer.write({ type: "text-end", id: textId });
          throw new DigigraphStreamContractError(
            digigraphErrorToEmbedPayload(dgErr as DigigraphErrorPayload),
          );
        }
        const c = delta.content;
        if (typeof c === "string" && c.length) {
          const cleaned = stripToolDumpFromAnswerDelta(c);
          if (cleaned.length) {
            writer.write({ type: "text-delta", id: textId, delta: cleaned });
          }
        }
        const tr = delta.digigraph_trace;
        if (tr && typeof tr === "object") {
          const payload = tr as DigigraphTracePayload;

          // #2306 follow-up: a round_boundary trace marks that the content already
          // streamed for that round (if any — digigraph only fires this when the
          // round narrated something) was NOT the final answer, e.g. "I will load
          // the full notes now." written alongside that round's tool calls. Without
          // this, that narration and the next round's real answer land in the SAME
          // text part with nothing between them — confirmed in production, where
          // they read as one continuous, self-contradicting block ("...I cannot
          // fully answer... [answers fully anyway]"). Closing the current text part
          // and opening a fresh one puts them in separate message parts instead.
          // This is NOT an activity span — it renders no visible chip; it only
          // resets which text part subsequent "content" deltas land in.
          if (payload.type === "round_boundary") {
            writer.write({ type: "text-end", id: textId });
            textId = `assistant-main-${++textSeq}`;
            writer.write({ type: "text-start", id: textId });
            continue;
          }

          for (const span of mapDigigraphTraceToSpans(payload, opts.activityDetail)) {
            writer.write({
              type: ACTIVITY_PART_TYPE,
              id: `dg-activity-${activitySeq++}`,
              data: span,
            });
          }
        }
      }
      writer.write({ type: "text-end", id: textId });
    },
  });

  return createUIMessageStreamResponse({ stream, headers: opts.responseHeaders });
}
