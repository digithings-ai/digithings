/** Exact MCP / backend tool ids for tool-row titles. Do not humanize. */

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

export function toolRowTitle(
  toolName: string,
  _input?: Record<string, unknown>,
): string {
  void _input;
  const name = toolName.trim();
  return name || "tool";
}
