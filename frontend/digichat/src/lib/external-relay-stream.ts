/**
 * External relay backend adapter: translates the DataTapStream-style relay
 * SSE contract (event: conversation|text-delta|trace|done|error) into an AI
 * SDK UI message stream. The relay holds conversation history server-side
 * (Azure Foundry conversations), so each turn sends only the latest user
 * message plus the conversation id echoed by the client
 * (X-External-Conversation, stored in sessionStorage by /embed).
 */
import {
  createUIMessageStream,
  createUIMessageStreamResponse,
  type UIMessage,
} from "ai";

export type RelayEvent = { event: string; data: Record<string, unknown> };

export async function* parseRelaySse(
  body: ReadableStream<Uint8Array>
): AsyncGenerator<RelayEvent> {
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
      let event = "";
      let dataRaw = "";
      for (const line of block.split("\n")) {
        if (line.startsWith("event: ")) event = line.slice(7).trim();
        else if (line.startsWith("data: ")) dataRaw = line.slice(6);
      }
      if (!event || !dataRaw) continue;
      try {
        yield { event, data: JSON.parse(dataRaw) as Record<string, unknown> };
      } catch {
        /* skip malformed frame */
      }
    }
  }
}

export function lastUserMessageText(messages: UIMessage[]): string {
  for (let i = messages.length - 1; i >= 0; i--) {
    const m = messages[i];
    if (m.role !== "user") continue;
    return m.parts
      .filter((p): p is { type: "text"; text: string } => p.type === "text")
      .map((p) => p.text)
      .join("\n")
      .trim();
  }
  return "";
}

export async function createExternalRelayStreamResponse(opts: {
  relayUrl: string;
  messages: UIMessage[];
  conversationId: string | null;
  responseHeaders: Record<string, string>;
  signal?: AbortSignal;
}): Promise<Response> {
  const message = lastUserMessageText(opts.messages);

  const stream = createUIMessageStream({
    onError: (error) =>
      error instanceof Error ? error.message : "external relay error",
    execute: async ({ writer }) => {
      const textId = "assistant-main";
      let textOpen = false;
      const openText = () => {
        if (!textOpen) {
          writer.write({ type: "text-start", id: textId });
          textOpen = true;
        }
      };
      const closeText = () => {
        if (textOpen) {
          writer.write({ type: "text-end", id: textId });
          textOpen = false;
        }
      };

      const res = await fetch(opts.relayUrl, {
        method: "POST",
        headers: { "content-type": "application/json" },
        body: JSON.stringify({ conversationId: opts.conversationId, message }),
        signal: opts.signal,
      });

      if (!res.ok || !res.body) {
        const detail = res.body ? (await res.text().catch(() => "")).trim() : "";
        openText();
        writer.write({
          type: "text-delta",
          id: textId,
          delta: `Upstream error: ${res.status} ${res.statusText}${
            detail ? `\n${detail.slice(0, 500)}` : ""
          }`,
        });
        closeText();
        return;
      }

      let traceSeq = 0;
      try {
        for await (const { event, data } of parseRelaySse(res.body)) {
          if (event === "conversation" && typeof data.conversationId === "string") {
            writer.write({
              type: "data-externalConversation",
              id: "relay-conversation",
              data: { conversationId: data.conversationId },
            });
          } else if (event === "text-delta" && typeof data.delta === "string") {
            openText();
            writer.write({ type: "text-delta", id: textId, delta: data.delta });
          } else if (event === "trace") {
            writer.write({
              type: "data-digigraphTrace",
              id: `relay-trace-${traceSeq++}`,
              data: {
                v: 1,
                type: "external_activity",
                service: "external",
                payload: { label: data.label, status: data.status },
              },
            });
          } else if (event === "error") {
            throw new Error(
              typeof data.message === "string" ? data.message : "external relay error"
            );
          } else if (event === "done") {
            break;
          }
        }
      } finally {
        closeText();
      }
    },
  });

  return createUIMessageStreamResponse({ stream, headers: opts.responseHeaders });
}
