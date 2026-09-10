/** Humanized tool-row titles for the embed tool chain. Keep `toolName` ids stable. */

export function searchMethodFromArgs(
  input?: Record<string, unknown>,
): "semantic" | "keyword" | "hybrid" {
  const raw =
    (typeof input?.mode === "string" && input.mode) ||
    (typeof input?.search_mode === "string" && input.search_mode) ||
    (typeof input?.search_type === "string" && input.search_type) ||
    "";
  const mode = raw.trim().toLowerCase();
  if (mode === "keyword" || mode === "bm25" || mode === "fts") return "keyword";
  if (mode === "hybrid") return "hybrid";
  // Default locate path is vector/semantic (digisearch orchestrator description).
  return "semantic";
}

export function toolRowTitle(
  toolName: string,
  input?: Record<string, unknown>,
): string {
  const name = toolName.trim();
  if (!name) return "tool";
  if (name === "web_search") return "web search";
  if (name === "digivault_search_notes" || name === "digivault") {
    return "digivault search notes";
  }
  if (name === "digivault_get_note") return "digivault get note";
  if (name === "digithings_docs" || name === "digisearch" || name.startsWith("digisearch")) {
    const method = searchMethodFromArgs(input);
    if (name === "digisearch_fetch_all") return `digisearch fetch all (${method})`;
    if (name === "digisearch_research_delegate") return `digisearch research (${method})`;
    return `digisearch ${method}`;
  }
  return name.replaceAll("_", " ");
}
