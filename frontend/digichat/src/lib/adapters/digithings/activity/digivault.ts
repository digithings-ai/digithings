import type { ActivitySpan } from "@/lib/chat-activity";
import { mapRawSourceToDocument } from "./source-document";

/**
 * Map digivault digigraph tool/trace payloads onto ActivitySpan.
 * digivault is reached only via digigraph (`digivault_hub` / digivault_search_notes)
 * — never as a digichat HTTP backend.
 */
export function mapDigivaultSearchNotes(
  payload: Record<string, unknown>
): ActivitySpan | null {
  const hits = payload.hits ?? payload.results ?? payload.notes;
  if (!Array.isArray(hits) || !hits.length) {
    const query =
      typeof payload.query === "string" && payload.query.trim()
        ? payload.query.trim()
        : undefined;
    if (payload.status === "started" || payload.status === "in_progress") {
      return {
        operation: "execute_tool",
        status: "started",
        label: "Searching digivault…",
        toolName: "digivault",
        ...(query ? { query } : {}),
      };
    }
    return null;
  }

  const documents = [];
  const seen = new Set<string>();
  for (const raw of hits) {
    if (!raw || typeof raw !== "object" || Array.isArray(raw)) continue;
    const h = raw as Record<string, unknown>;
    const doc = mapRawSourceToDocument({
      ...h,
      vault_path: h.vault_path ?? h.path,
      snippet:
        h.snippet ??
        (typeof h.body_markdown === "string" ? h.body_markdown.trim().slice(0, 280) : undefined),
      metadata: {
        ...(typeof h.metadata === "object" && h.metadata && !Array.isArray(h.metadata)
          ? (h.metadata as Record<string, unknown>)
          : {}),
        title: h.title,
        vault_path: h.vault_path ?? h.path,
      },
    });
    if (!doc || seen.has(doc.path)) continue;
    seen.add(doc.path);
    documents.push(doc);
  }
  if (!documents.length) return null;

  const query =
    typeof payload.query === "string" && payload.query.trim()
      ? payload.query.trim()
      : undefined;
  return {
    operation: "retrieve",
    status: "completed",
    label: "Sources",
    toolName: "digivault",
    documents,
    ...(query ? { query } : {}),
  };
}
