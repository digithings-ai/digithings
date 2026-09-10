/** Display labels for tool rows. Tool ids stay exact in toolName. */

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
  return "semantic";
}

function humanize(toolName: string): string {
  return toolName
    .replace(/^digivault_/, "digivault ")
    .replace(/^digisearch_/, "digisearch ")
    .replace(/_/g, " ")
    .trim();
}

export function toolRowTitle(
  toolName: string,
  input?: Record<string, unknown>,
): string {
  const name = toolName.trim();
  if (!name) return "tool";
  if (name === "digisearch" || name.startsWith("digisearch_")) {
    if (name === "digisearch_fetch_all" || name === "digisearch_research") {
      return humanize(name);
    }
    return `digisearch ${searchMethodFromArgs(input)}`;
  }
  if (name === "digivault_search_notes") return "digivault search notes";
  if (name === "digivault_get_note") return "digivault get note";
  if (name === "web_search") return "web search";
  return humanize(name) || "tool";
}
