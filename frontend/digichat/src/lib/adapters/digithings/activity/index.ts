import {
  applyActivityDetail,
  sanitizeActivitySpan,
  type ActivityDetail,
  type ActivitySpan,
} from "@/lib/chat-activity";
import { mapDigisearchRagSources } from "./digisearch";
import { mapDigivaultGetNote, mapDigivaultSearchNotes } from "./digivault";

export type DigigraphTraceLike = {
  type: string;
  payload?: Record<string, unknown>;
};

/** LangGraph housekeeping trace types — never shown in the activity chain. */
const SUPPRESSED_TRACE_TYPES = new Set(["graph_step", "span"]);

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

/**
 * Project digigraph SSE/trace events onto ActivitySpan. digivault and digisearch
 * contribute only as digigraph tools — see ./digivault.ts and ./digisearch.ts.
 */
export function mapDigigraphTraceToSpans(
  trace: DigigraphTraceLike,
  detail: ActivityDetail
): ActivitySpan[] {
  if (SUPPRESSED_TRACE_TYPES.has(trace.type)) return [];

  let raw: ActivitySpan | null = null;
  if (trace.type === "tool_call") {
    const payload = trace.payload ?? {};
    const tool =
      (typeof payload.tool === "string" && payload.tool.trim()) ||
      (typeof payload.toolName === "string" && payload.toolName.trim()) ||
      (typeof payload.name === "string" && payload.name.trim()) ||
      "";
    if (!tool) return [];
    const query =
      typeof payload.query === "string" && payload.query.trim()
        ? payload.query.trim()
        : undefined;
    raw = {
      operation: "execute_tool",
      status: payload.status === "completed" ? "completed" : "started",
      label: tool,
      toolName: tool,
      ...(query ? { query } : {}),
    };
  } else if (trace.type === "rag_sources") {
    raw = mapDigisearchRagSources(trace.payload ?? {});
  } else if (
    trace.type === "digivault_get_note" ||
    trace.payload?.toolName === "digivault_get_note" ||
    trace.payload?.tool === "digivault_get_note"
  ) {
    raw = mapDigivaultGetNote(trace.payload ?? {});
    if (!raw) raw = mapOpaque(trace);
  } else if (
    trace.type === "digivault_search_notes" ||
    trace.type === "digivault" ||
    trace.payload?.toolName === "digivault_search_notes"
  ) {
    raw = mapDigivaultSearchNotes(trace.payload ?? {});
    if (!raw) raw = mapOpaque(trace);
  } else if (trace.type === "graph_update") {
    // Only research_brief graph_update events surface as "Research brief".
    // Bare LangGraph stream updates (payload.update) are internal housekeeping.
    raw = mapGraphUpdate(trace.payload ?? {});
  } else {
    raw = mapOpaque(trace);
  }
  if (!raw) return [];
  const sanitized = sanitizeActivitySpan(raw);
  if (!sanitized) return [];
  const gated = applyActivityDetail(sanitized, detail);
  return gated ? [gated] : [];
}

export { mapDigisearchRagSources } from "./digisearch";
export { mapDigivaultGetNote, mapDigivaultSearchNotes } from "./digivault";
