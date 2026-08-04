import {
  applyActivityDetail,
  sanitizeActivitySpan,
  type ActivityDetail,
  type ActivityDocument,
  type ActivitySpan,
} from "@/lib/chat-activity";

export type DigigraphTraceLike = {
  type: string;
  payload?: Record<string, unknown>;
};

function tierFromMeta(meta: Record<string, unknown>): string | undefined {
  const t = meta.evidence_tier;
  if (typeof t === "string" && t.trim()) return t.trim();
  if (meta.peer_reviewed === true) return "peer_reviewed";
  return undefined;
}

function mapRagSources(payload: Record<string, unknown>): ActivitySpan | null {
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

function mapGraphUpdate(payload: Record<string, unknown>): ActivitySpan | null {
  const briefRaw = payload.research_brief;
  if (!briefRaw || typeof briefRaw !== "object" || Array.isArray(briefRaw)) return null;
  const b = briefRaw as Record<string, unknown>;
  const themesIn = Array.isArray(b.themes) ? b.themes : [];
  const themes: { label: string; summary: string }[] = [];
  for (const entry of themesIn) {
    if (!entry || typeof entry !== "object" || Array.isArray(entry)) continue;
    const t = entry as Record<string, unknown>;
    const label = typeof t.label === "string" ? t.label : "";
    const summary = typeof t.summary === "string" ? t.summary : "";
    if (!label.trim() || !summary.trim()) continue;
    themes.push({ label: label.trim(), summary: summary.trim() });
  }
  if (!themes.length) return null;
  const questions = Array.isArray(payload.profiling_questions)
    ? payload.profiling_questions.filter((q): q is string => typeof q === "string" && !!q.trim())
    : undefined;
  return {
    operation: "chat",
    status: "completed",
    label: "Research brief",
    brief: {
      themes,
      ...(questions?.length ? { questions } : {}),
    },
  };
}

function mapOpaque(trace: DigigraphTraceLike): ActivitySpan {
  const label =
    (typeof trace.payload?.label === "string" && trace.payload.label) || trace.type || "activity";
  const status = trace.payload?.status === "completed" ? "completed" : "started";
  return { operation: "chat", status, label };
}

export function mapDigigraphTraceToSpans(
  trace: DigigraphTraceLike,
  detail: ActivityDetail
): ActivitySpan[] {
  let raw: ActivitySpan | null = null;
  if (trace.type === "rag_sources") {
    raw = mapRagSources(trace.payload ?? {});
  } else if (trace.type === "graph_update") {
    raw = mapGraphUpdate(trace.payload ?? {});
    if (!raw) raw = mapOpaque(trace);
  } else {
    raw = mapOpaque(trace);
  }
  if (!raw) return [];
  const sanitized = sanitizeActivitySpan(raw);
  if (!sanitized) return [];
  const gated = applyActivityDetail(sanitized, detail);
  return gated ? [gated] : [];
}
