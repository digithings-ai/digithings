/** Pretty-print tool args the same way results already use JSON.stringify(..., null, 2). */
export function formatJsonDump(value: unknown): string {
  if (value === undefined) return "";
  if (typeof value === "string") {
    const trimmed = value.trim();
    if (!trimmed) return value;
    try {
      return JSON.stringify(JSON.parse(trimmed), null, 2);
    } catch {
      return value;
    }
  }
  try {
    return JSON.stringify(value, null, 2);
  } catch {
    return String(value);
  }
}

export function formatToolDurationMs(ms: number): string {
  if (!Number.isFinite(ms) || ms < 0) return "0ms";
  const rounded = Math.round(ms);
  if (rounded < 1000) return `${rounded}ms`;
  const seconds = rounded / 1000;
  if (seconds < 10) return `${(Math.floor(seconds * 10) / 10).toFixed(1)}s`;
  if (seconds < 60) return `${Math.floor(seconds)}s`;
  return `${Math.floor(seconds / 60)}m ${Math.floor(seconds % 60)}s`;
}

export function humanizeToolName(toolName: string, argsText?: string): string {
  let input: Record<string, unknown> | undefined;
  if (argsText) {
    try {
      const parsed: unknown = JSON.parse(argsText);
      if (parsed && typeof parsed === "object" && !Array.isArray(parsed)) {
        input = parsed as Record<string, unknown>;
      }
    } catch {
      /* compact or non-JSON args */
    }
  }
  const name = toolName.trim();
  if (name === "web_search") return "web search";
  if (name === "digivault_search_notes" || name === "digivault") return "digivault search notes";
  if (name === "digivault_get_note") return "digivault get note";
  if (name === "digithings_docs" || name === "digisearch" || name.startsWith("digisearch")) {
    const raw =
      (typeof input?.mode === "string" && input.mode) ||
      (typeof input?.search_mode === "string" && input.search_mode) ||
      (typeof input?.search_type === "string" && input.search_type) ||
      "";
    const mode = raw.trim().toLowerCase();
    const method =
      mode === "keyword" || mode === "bm25" || mode === "fts"
        ? "keyword"
        : mode === "hybrid"
          ? "hybrid"
          : "semantic";
    if (name === "digisearch_fetch_all") return `digisearch fetch all (${method})`;
    if (name === "digisearch_research") return `digisearch research (${method})`;
    return `digisearch ${method}`;
  }
  return name.replaceAll("_", " ");
}
