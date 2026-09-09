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
import { type ActivityDetail } from "@/lib/chat-activity";
import { mapDigigraphTraceToSpans } from "@/lib/adapters/digithings/activity";
import {
  createActivityWriteContext,
  finishStandardActivity,
  uiMessagesForUpstream,
  writeStandardActivity,
} from "@/lib/ui-stream-parts";
import { BYOK_MODEL_REMEDIABLE_CODES } from "@/lib/embed-chat-error";

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
  // BYOK remediable codes carry trusted copy in embed-chat-error — never relay
  // digigraph's message (it can echo caller headers or other upstream detail).
  if (
    typeof err.message === "string" &&
    err.message.length &&
    !BYOK_MODEL_REMEDIABLE_CODES.has(code)
  ) {
    payload.message = err.message;
  }
  return JSON.stringify(payload);
}

/**
 * The one upstream-body field an embed visitor is allowed to see: a refusal code
 * the frontend already knows how to act on.
 *
 * Everything else about a digigraph error body stays server-side (see the
 * `!res.ok` branch below). These codes are the exception because
 * `BYOK_MODEL_REMEDIABLE_CODES` — the same set, imported rather than copied, so
 * the two cannot drift — is what `embed-chat-error` uses to open the BYOK
 * sequence and to pick the copy. A code with no frontend copy would render as
 * raw JSON, which is worse than the generic message.
 *
 * The code is relayed; the message never is. digigraph's message for
 * `byok_default_model_provider_mismatch` reflects the caller's own
 * `X-BYOK-Provider` header, and a 500 body can carry stack traces and prompt
 * echoes.
 */
function relayableUpstreamCode(body: string): string | null {
  if (!body.length) return null;
  let parsed: unknown;
  try {
    parsed = JSON.parse(body);
  } catch {
    return null;
  }
  if (typeof parsed !== "object" || parsed === null) return null;
  // digibase's json_error_response nests: {"error": {"code": ..., "message": ...}}.
  // Flat {"code": ...} is accepted too, for handlers that answer without it.
  const outer = parsed as { error?: unknown; code?: unknown };
  const inner =
    typeof outer.error === "object" && outer.error !== null
      ? (outer.error as { code?: unknown })
      : undefined;
  const code = typeof inner?.code === "string" ? inner.code : outer.code;
  if (typeof code !== "string" || !BYOK_MODEL_REMEDIABLE_CODES.has(code)) return null;
  return code;
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
  /** Includes the upstream `Authorization`; route.ts always builds it. */
  upstreamHeaders: Record<string, string>;
  responseHeaders: Record<string, string>;
  activityDetail: ActivityDetail;
  /** AbortSignal from the inbound request — Stop must cancel the digigraph fetch (#3475). */
  signal?: AbortSignal;
}) {
  const stripped = uiMessagesForUpstream(opts.messages).map((m) => {
    const { id: _omit, ...rest } = m;
    void _omit;
    return rest;
  }) as Omit<UIMessage, "id">[];
  const coreMessages = await convertToModelMessages(stripped, {
    ignoreIncompleteToolCalls: true,
  });
  const url = digigraphChatCompletionsUrl(opts.digigraphBaseUrl);
  const model = digigraphModelName();

  const stream = createUIMessageStream({
    onError: (error) => (error instanceof Error ? error.message : "digigraph stream error"),
    execute: async ({ writer }) => {
      let textSeq = 0;
      let textId = "assistant-main";
      writer.write({ type: "text-start", id: textId });
      const activityCtx = createActivityWriteContext();
      const bodyPayload: Record<string, unknown> = {
        model,
        messages: coreMessagesToDigigraphOpenAi(coreMessages),
        stream: true,
      };
      const res = await fetch(url, {
        method: "POST",
        headers: {
          "Content-Type": "application/json",
          // Authorization comes from upstreamHeaders and nowhere else, because
          // route.ts sets it unconditionally (`route.ts:244`, one const literal;
          // later lines only add X-* keys). NOT because the spread would override
          // it — a spread overrides only keys it actually contains, so an
          // `Authorization` set here WOULD survive a caller that omitted one. That
          // is why route.ts's unconditional set is pinned by a test rather than
          // left to inspection: if it ever becomes conditional, this adapter must
          // regain a fallback or digigraph gets an unauthenticated request (#2537).
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
        signal: opts.signal,
      });
      if (!res.ok) {
        // Log the upstream detail server-side; never stream it. A 500 body can
        // carry stack traces, internal hostnames, and prompt echoes, and this
        // response goes to anonymous embed visitors.
        const detail = (await res.text().catch(() => "")).trim();
        console.error(
          `[digigraph] upstream ${res.status} ${res.statusText}`,
          detail.length > 1500 ? `${detail.slice(0, 1500)}…` : detail
        );
        const relayable = relayableUpstreamCode(detail);
        if (relayable) {
          // Actionable refusal: hand the code (never the body) to the client so
          // it can say what to do instead of a dead end. Same mechanism as the
          // `digigraph_error` SSE branch below; both now drop upstream `message`
          // for BYOK remediable codes (embed-chat-error owns that copy).
          writer.write({ type: "text-end", id: textId });
          throw new DigigraphStreamContractError(
            digigraphErrorToEmbedPayload({ code: relayable })
          );
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
            writeStandardActivity(writer, span, activityCtx);
          }
        }
      }
      finishStandardActivity(writer, activityCtx);
      writer.write({ type: "text-end", id: textId });
    },
  });

  return createUIMessageStreamResponse({ stream, headers: opts.responseHeaders });
}
