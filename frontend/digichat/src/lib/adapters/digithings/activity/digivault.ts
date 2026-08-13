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
    // Still surface digivault_get_note batch errors (notes may be absent while
    // errors is present) and in-flight "Searching digivault…" spans.
    const errors = payload.errors;
    if (errors && typeof errors === "object" && !Array.isArray(errors)) {
      const paths = Object.keys(errors as Record<string, unknown>);
      if (paths.length > 0) {
        return {
          operation: "retrieve",
          status: "failed",
          label: `digivault errors (${paths.length})`,
          toolName: "digivault",
          ...(query ? { query } : {}),
          hitCount: paths.length,
        };
      }
    }
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
  const errors =
    payload.errors && typeof payload.errors === "object" && !Array.isArray(payload.errors)
      ? (payload.errors as Record<string, unknown>)
      : undefined;
  const errorCount = errors ? Object.keys(errors).length : 0;
  // A zero-hit search (`hits: []`, explicitly present) reaches here too —
  // same reasoning as mapDigisearchRagSources next door: omitting `documents`
  // (rather than early-returning null) is what lets toDigiChatActivity's
  // retrieve branch render the honest `count: 0` "no hits" row instead of
  // dropping the span outright. Partial batch failures keep successful notes
  // and surface error count via hitCount when documents mapped empty.
  return {
    operation: "retrieve",
    status: errorCount > 0 && documents.length === 0 ? "failed" : "completed",
    label:
      errorCount > 0 && documents.length > 0
        ? `Sources (${errorCount} errors)`
        : errorCount > 0
          ? `digivault errors (${errorCount})`
          : "Sources",
    toolName: "digivault",
    ...(documents.length ? { documents } : {}),
    ...(!documents.length && errorCount > 0 ? { hitCount: errorCount } : {}),
    ...(query ? { query } : {}),
  };
}
