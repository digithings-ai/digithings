/** Tool-row titles: raw backend tool ids, except dedicated digisearch_* tools. */

// Built-in digisearch tools keep their exact backend id.
const VERBATIM = new Set(["digisearch_fetch_all", "digisearch_research", "digisearch_research_delegate"]);
const ACRONYMS = new Set(["occ", "faq", "pdf", "api", "mcp"]);

export function toolRowTitle(toolName: string): string {
  const name = toolName.trim();
  if (!name) return "tool";
  // Per-index search tools (DIG-3269): digisearch_zammad_tickets ->
  // "DigiSearch Zammad Tickets", digisearch_occ_help -> "DigiSearch OCC Help".
  const m = /^digisearch_([a-z0-9_]+)$/i.exec(name);
  if (m && !VERBATIM.has(name)) {
    const words = m[1]
      .split("_")
      .filter(Boolean)
      .map((w) =>
        ACRONYMS.has(w.toLowerCase()) ? w.toUpperCase() : w[0].toUpperCase() + w.slice(1),
      );
    return ["DigiSearch", ...words].join(" ");
  }
  return name;
}
