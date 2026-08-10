import type { ActivitySpan } from "@/lib/chat-activity";
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
  if (!documents.length) return null;
  const toolName = ragToolDisplayName(payload.tool);
  const query =
    typeof payload.query === "string" && payload.query.trim()
      ? payload.query.trim()
      : undefined;
  return {
    operation: "retrieve",
    status: "completed",
    label: "Sources",
    toolName,
    documents,
    ...(query ? { query } : {}),
  };
}
