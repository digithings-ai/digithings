import {
  convertToModelMessages,
  createUIMessageStream,
  createUIMessageStreamResponse,
  type UIMessage,
} from "ai";
import {
  digigraphChatCompletionsUrl,
  digigraphModelName,
  digigraphOpenWebUIFormat,
} from "@/lib/digigraph";
import { coreMessagesToDigigraphOpenAi } from "@/lib/digigraph-messages";
import {
  ACTIVITY_PART_TYPE,
  chatActivitySpan,
  type ActivityDetail,
} from "@/lib/chat-activity";

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
  emitLegacyTracePart: boolean;
}) {
  const openwebui = digigraphOpenWebUIFormat();
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
    execute: async ({ writer }) => {
      const textId = "assistant-main";
      writer.write({ type: "text-start", id: textId });
      let traceSeq = 0;
      let activitySeq = 0;
      const bodyPayload: Record<string, unknown> = {
        model,
        messages: coreMessagesToDigigraphOpenAi(coreMessages),
        stream: true,
      };
      if (openwebui) bodyPayload.openwebui_format = true;
      const res = await fetch(url, {
        method: "POST",
        headers: {
          "Content-Type": "application/json",
          Authorization: `Bearer ${apiKey}`,
          ...opts.upstreamHeaders,
          ...(openwebui ? { "X-Response-Format": "openwebui" } : {}),
        },
        body: JSON.stringify(bodyPayload),
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
        const c = delta.content;
        if (typeof c === "string" && c.length) {
          writer.write({ type: "text-delta", id: textId, delta: c });
        }
        const tr = delta.digigraph_trace;
        if (tr && typeof tr === "object") {
          const payload = tr as DigigraphTracePayload;

          // Legacy part: authenticated-path-only, emitted with the verbatim
          // upstream payload. This is the pre-existing authenticated-path
          // behaviour that chat-panel.tsx's rich renderers (RagSourcesTrace,
          // ResearchBriefTrace) depend on for their full payload, so it must
          // NOT be routed through applyActivityDetail like the span below —
          // chat-panel.tsx has no notion of activity detail levels, only the
          // embed surface does. Embed paths get the gated activity span alone.
          // Remove this block (and the resulting dual-emit) once chat-panel.tsx
          // migrates to rendering ACTIVITY_PART_TYPE directly.
          if (opts.emitLegacyTracePart) {
            writer.write({
              type: "data-digigraphTrace",
              id: `dg-trace-${traceSeq++}`,
              data: payload,
            });
          }

          // New part: gated by this tenant's activityDetail, same as every
          // other provider.
          const span = chatActivitySpan(
            payload.payload?.label ?? payload.type,
            payload.payload?.status === "completed" ? "completed" : "started",
            opts.activityDetail
          );
          if (span) {
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
