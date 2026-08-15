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
        // All-error batch (notes absent): emit execute_tool/failed so
        // toDigiChatActivity's failure path renders "Search … failed." —
        // never overload hitCount with an error count (that field means
        // upstream digisearch hit_count when documents mapped empty).
        return {
          operation: "execute_tool",
          status: "failed",
          label: `digivault errors (${paths.length})`,
          toolName: "digivault",
          ...(query ? { query } : {}),
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
  // dropping the span outright. All-error batches (notes present but every
  // entry failed mapping, or notes: [] with errors) use execute_tool/failed
  // so the UI shows a failure rather than a fake hit count.
  if (errorCount > 0 && documents.length === 0) {
    return {
      operation: "execute_tool",
      status: "failed",
      label: `digivault errors (${errorCount})`,
      toolName: "digivault",
      ...(query ? { query } : {}),
    };
  }
  return {
    operation: "retrieve",
    status: "completed",
    label:
      errorCount > 0 ? `Sources (${errorCount} errors)` : "Sources",
    toolName: "digivault",
    ...(documents.length ? { documents } : {}),
    ...(query ? { query } : {}),
  };
}
