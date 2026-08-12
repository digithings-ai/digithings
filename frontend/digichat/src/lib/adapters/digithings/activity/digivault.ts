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
  const query =
    typeof payload.query === "string" && payload.query.trim()
      ? payload.query.trim()
      : undefined;

  if (!Array.isArray(hits)) {
    // No hits/results/notes key at all — not a completed search result.
    // Still surface an in-flight "Searching digivault…" span when one is
    // signaled; otherwise this payload isn't a digivault_search_notes trace
    // this mapper understands.
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
  // A zero-hit search (`hits: []`, explicitly present) reaches here too —
  // same reasoning as mapDigisearchRagSources next door: omitting `documents`
  // (rather than early-returning null) is what lets toDigiChatActivity's
  // retrieve branch render the honest `count: 0` "no hits" row instead of
  // dropping the span outright.
  return {
    operation: "retrieve",
    status: "completed",
    label: "Sources",
    toolName: "digivault",
    ...(documents.length ? { documents } : {}),
    ...(query ? { query } : {}),
  };
}
