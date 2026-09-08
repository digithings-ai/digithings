import type { ActivitySpan } from "@/lib/chat-activity";
import { mapDigivaultGetNote, DIGIVAULT_GET_NOTE_TOOL } from "./digivault";
import {
  mapRawSourceToDocument,
  ragToolDisplayName,
} from "./source-document";

/**
 * Map digisearch-style digigraph traces (`rag_sources`) onto ActivitySpan.
 * digisearch is a digigraph tool — not a digichat HTTP backend.
 */
export function mapDigisearchRagSources(
  payload: Record<string, unknown>
): ActivitySpan | null {
  const toolRaw = typeof payload.tool === "string" ? payload.tool.trim() : "";
  if (toolRaw === DIGIVAULT_GET_NOTE_TOOL) {
    return mapDigivaultGetNote(payload);
  }
  const sources = payload.sources;
  if (!Array.isArray(sources)) return null;
  const documents = [];
  const seen = new Set<string>();
  for (const raw of sources) {
    if (!raw || typeof raw !== "object" || Array.isArray(raw)) continue;
    const doc = mapRawSourceToDocument(raw as Record<string, unknown>);
    if (!doc || seen.has(doc.path)) continue;
    seen.add(doc.path);
    documents.push(doc);
  }
  const toolName = ragToolDisplayName(payload.tool);
  const query =
    typeof payload.query === "string" && payload.query.trim()
      ? payload.query.trim()
      : undefined;
  // A zero-hit search (`sources: []`) reaches here too — digigraph now emits
  // this trace on every completed retrieval, hit or miss (workflow.py's
  // `"rag_sources" in data` gate, not `data.get("rag_sources")`), so it must
  // render as a visible "searched, found nothing" row rather than being
  // dropped, or a user cannot tell that apart from "the model never
  // searched". Omitting `documents` (rather than early-returning null) is
  // enough: toDigiChatActivity's retrieve branch already turns a
  // documents-less completed retrieve span into a `tool_result` with
  // `count: 0`, which the shared UI's `outcomeMeta` renders as the literal
  // "no hits" string — the same outcome a genuinely-empty search gets today
  // via the trailing settle pass, just reached directly instead of via a
  // started/completed execute_tool pair (digisearch/digivault never emit
  // one).
  //
  // `hit_count` rides along on this payload (see digigraph's workflow.py).
  // Prefer documents.length when mapping produced docs; when mapping yields
  // zero documents but upstream reported a positive hit_count (sources lacked
  // usable path/title), keep that count so the UI does not say "no hits".
  const upstreamHits =
    typeof payload.hit_count === "number" &&
    Number.isFinite(payload.hit_count) &&
    payload.hit_count > 0
      ? Math.trunc(payload.hit_count)
      : undefined;
  return {
    operation: "retrieve",
    status: "completed",
    label: "Sources",
    toolName,
    ...(documents.length ? { documents } : {}),
    ...(!documents.length && upstreamHits ? { hitCount: upstreamHits } : {}),
    ...(query ? { query } : {}),
  };
}
