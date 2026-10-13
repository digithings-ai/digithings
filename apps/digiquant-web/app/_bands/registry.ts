/** Ordered bands of the home page. page.tsx, SectionRail and the nav all read this
 *  list; band files edit only their own band. The order is the showcase story:
 *  the hero, the dashboard and the method behind its runs (adjacent), how a
 *  strategy is built in chat, the MCP tooling underneath, the tearsheets it
 *  produces, the integrations (the only band that names them), and how to start. */
export type BandId = "top" | "dashboard" | "pipeline" | "chat" | "mcp" | "tearsheets" | "integrations" | "start";

export const BANDS: readonly { id: BandId; label: string }[] = [
  { id: "top", label: "top" },
  { id: "dashboard", label: "dashboard" },
  { id: "pipeline", label: "pipeline" },
  { id: "chat", label: "chat" },
  { id: "mcp", label: "mcp" },
  { id: "tearsheets", label: "tearsheets" },
  { id: "integrations", label: "integrations" },
  { id: "start", label: "start" },
];
