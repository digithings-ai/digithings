import type { ActivityDocument, ActivitySpan } from "@/lib/chat-activity";

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
        toolName: "digivault_search_notes",
        ...(query ? { query } : {}),
      };
    }
    return null;
  }

  const documents: ActivityDocument[] = [];
  for (const raw of hits) {
    if (!raw || typeof raw !== "object" || Array.isArray(raw)) continue;
    const h = raw as Record<string, unknown>;
    const path =
      (typeof h.vault_path === "string" && h.vault_path.trim()) ||
      (typeof h.path === "string" && h.path.trim()) ||
      "";
    const title =
      (typeof h.title === "string" && h.title.trim()) || path;
    if (!path || !title) continue;
    const doc: ActivityDocument = { title, path };
    if (typeof h.snippet === "string" && h.snippet.trim()) {
      doc.snippet = h.snippet.trim();
    } else if (typeof h.body_markdown === "string" && h.body_markdown.trim()) {
      doc.snippet = h.body_markdown.trim().slice(0, 280);
    }
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
    label: "digivault hits",
    toolName: "digivault_search_notes",
    documents,
    ...(query ? { query } : {}),
  };
}
