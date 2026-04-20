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
        let detail = "";
        try {
          detail = (await res.text()).trim();
        } catch {
          /* ignore */
        }
        const brief =
          detail.length > 1500 ? `${detail.slice(0, 1500)}…` : detail;
        writer.write({
          type: "text-delta",
          id: textId,
          delta: brief
            ? `Upstream error: ${res.status} ${res.statusText}\n${brief}`
            : `Upstream error: ${res.status} ${res.statusText}`,
        });
        writer.write({ type: "text-end", id: textId });
        return;
      }
      if (!res.body) {
        writer.write({
          type: "text-delta",
          id: textId,
          delta: `Upstream error: ${res.status} empty response body`,
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
          writer.write({
            type: "data-digigraphTrace",
            id: `dg-trace-${traceSeq++}`,
            data: tr as DigigraphTracePayload,
          });
        }
      }
      writer.write({ type: "text-end", id: textId });
    },
  });

  return createUIMessageStreamResponse({ stream, headers: opts.responseHeaders });
}
