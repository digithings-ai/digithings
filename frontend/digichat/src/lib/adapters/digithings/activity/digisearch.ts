import type { ActivityDocument, ActivitySpan } from "@/lib/chat-activity";

function tierFromMeta(meta: Record<string, unknown>): string | undefined {
  const t = meta.evidence_tier;
  if (typeof t === "string" && t.trim()) return t.trim();
  if (meta.peer_reviewed === true) return "peer_reviewed";
  return undefined;
}

/**
 * Map digisearch-style digigraph traces (`rag_sources`) onto ActivitySpan.
 * digisearch is a digigraph tool — not a digichat HTTP backend.
 */
export function mapDigisearchRagSources(
  payload: Record<string, unknown>
): ActivitySpan | null {
  const sources = payload.sources;
  if (!Array.isArray(sources)) return null;
  const documents: ActivityDocument[] = [];
  for (const raw of sources) {
    if (!raw || typeof raw !== "object" || Array.isArray(raw)) continue;
    const s = raw as Record<string, unknown>;
    const meta =
      s.metadata && typeof s.metadata === "object" && !Array.isArray(s.metadata)
        ? (s.metadata as Record<string, unknown>)
        : {};
    const path =
      (typeof s.source_id === "string" && s.source_id.trim()) ||
      (typeof s.doc_id === "string" && s.doc_id.trim()) ||
      "";
    const title =
      (typeof meta.title === "string" && meta.title.trim()) ||
      (typeof meta.doi_or_arxiv === "string" && meta.doi_or_arxiv.trim()) ||
      path;
    if (!path || !title) continue;
    const doc: ActivityDocument = { title, path };
    const tier = tierFromMeta(meta);
    if (tier) doc.tier = tier;
    if (typeof meta.publication_year === "number" && Number.isFinite(meta.publication_year)) {
      doc.year = Math.trunc(meta.publication_year);
    }
    if (typeof s.snippet === "string" && s.snippet.trim()) {
      doc.snippet = s.snippet.trim();
    }
    documents.push(doc);
  }
  if (!documents.length) return null;
  return {
    operation: "retrieve",
    status: "completed",
    label: "Sources",
    toolName: "rag_sources",
    documents,
  };
}
