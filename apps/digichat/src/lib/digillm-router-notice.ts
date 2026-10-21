/**
 * Attach digillm's routing decision to a chat response.
 *
 * Headers are always set. A UI message stream also gains one `data-status`
 * part after its first event, which the thread already renders as a status
 * line (`message` + `detail`). Other body types are left alone.
 */

import type { DigillmRouterDecision } from "@/lib/digillm-router";

function headerReason(reason: string): string {
  return reason.replace(/[\r\n]+/g, " ").slice(0, 180);
}

export function withDigillmRouterNotice(
  res: Response,
  decision: DigillmRouterDecision,
): Response {
  const headers = new Headers(res.headers);
  headers.set("x-digillm-router-route", decision.routeId);
  headers.set("x-digillm-router-model", decision.model);
  headers.set("x-digillm-router-reason", headerReason(decision.reason));

  const contentType = res.headers.get("content-type") ?? "";
  if (!res.body || !contentType.includes("text/event-stream")) {
    return new Response(res.body, {
      status: res.status,
      statusText: res.statusText,
      headers,
    });
  }

  const encoder = new TextEncoder();
  const decoder = new TextDecoder();
  let pending = "";
  let injected = false;
  const notice = `data: ${JSON.stringify({
    type: "data-status",
    id: "digillm-router",
    data: {
      message: `Router · ${decision.label} · ${decision.model}`,
      detail: decision.reason,
    },
  })}\n\n`;

  const stream = res.body.pipeThrough(
    new TransformStream<Uint8Array, Uint8Array>({
      transform(chunk, controller) {
        if (injected) {
          controller.enqueue(chunk);
          return;
        }
        pending += decoder.decode(chunk, { stream: true });
        const split = pending.indexOf("\n\n");
        if (split === -1) return;
        const first = pending.slice(0, split + 2);
        const rest = pending.slice(split + 2);
        pending = "";
        injected = true;
        const body = first.startsWith("data:") ? `${first}${notice}${rest}` : `${first}${rest}`;
        controller.enqueue(encoder.encode(body));
      },
      flush(controller) {
        if (pending) controller.enqueue(encoder.encode(pending));
      },
    }),
  );

  return new Response(stream, {
    status: res.status,
    statusText: res.statusText,
    headers,
  });
}
