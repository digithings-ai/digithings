/**
 * Maps Cloudflare digivault NDJSON chat events onto digichat server events
 * (activity spans / text / quota / done). Used for fixture parity and as the
 * conceptual bridge while the Node stream emits AI SDK parts directly.
 */
import type { ActivitySpan } from "./chat-activity";

export type DigivaultServerEvent =
  | { type: "text-delta"; delta: string }
  | { type: "activity"; span: ActivitySpan }
  | { type: "quota_exhausted"; message: string }
  | { type: "error"; message: string }
  | { type: "done" };

export function mapDigivaultNdjsonEvent(event: unknown): DigivaultServerEvent | null {
  if (!event || typeof event !== "object" || Array.isArray(event)) return null;
  const e = event as Record<string, unknown>;
  const type = e.type;

  if (type === "status") {
    const message = typeof e.message === "string" && e.message.trim() ? e.message.trim() : "status";
    return {
      type: "activity",
      span: { operation: "chat", status: "started", label: message },
    };
  }

  if (type === "tool_call") {
    const name = typeof e.name === "string" && e.name.trim() ? e.name.trim() : "tool";
    const query = typeof e.query === "string" ? e.query : "";
    return {
      type: "activity",
      span: {
        operation: "execute_tool",
        status: "started",
        label: "Searching digivault…",
        toolName: name,
        query,
      },
    };
  }

  if (type === "tool_result") {
    const name = typeof e.name === "string" && e.name.trim() ? e.name.trim() : "search_digivault";
    const query = typeof e.query === "string" ? e.query : "";
    const documents: ActivitySpan["documents"] = [];
    if (Array.isArray(e.hits)) {
      for (const hit of e.hits) {
        if (!hit || typeof hit !== "object" || Array.isArray(hit)) continue;
        const h = hit as Record<string, unknown>;
        const title = typeof h.title === "string" ? h.title : "";
        const path = typeof h.path === "string" ? h.path : "";
        if (!title || !path) continue;
        documents.push({ title, path });
      }
    }
    return {
      type: "activity",
      span: {
        operation: "retrieve",
        status: "completed",
        label: "Sources",
        toolName: name,
        query,
        ...(documents.length ? { documents } : {}),
      },
    };
  }

  if (type === "reasoning") {
    const delta = typeof e.delta === "string" ? e.delta : "";
    if (!delta) return null;
    return {
      type: "activity",
      span: {
        operation: "chat",
        status: "started",
        label: "reasoning",
        reasoningDelta: delta,
      },
    };
  }

  if (type === "content") {
    const delta = typeof e.delta === "string" ? e.delta : "";
    if (!delta) return null;
    return { type: "text-delta", delta };
  }

  if (type === "quota_exhausted") {
    const message =
      typeof e.message === "string" && e.message.trim()
        ? e.message.trim()
        : "quota exhausted";
    return { type: "quota_exhausted", message };
  }

  if (type === "error") {
    const message =
      typeof e.message === "string" && e.message.trim()
        ? e.message.trim()
        : "chat failed";
    return { type: "error", message };
  }

  if (type === "done") {
    return { type: "done" };
  }

  return null;
}
