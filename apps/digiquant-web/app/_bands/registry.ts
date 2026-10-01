/** Ordered bands of the home page. page.tsx, SectionRail and the nav all read this
 *  list; band files edit only their own band. The order is the showcase story:
 *  the dashboard first (it is the product), then how work gets built in it, the
 *  method behind each run, what a run produces, and the tooling underneath. */
export type BandId = "top" | "dashboard" | "workflow" | "pipeline" | "tearsheets" | "tooling" | "start";

export const BANDS: readonly { id: BandId; label: string }[] = [
  { id: "top", label: "top" },
  { id: "dashboard", label: "dashboard" },
  { id: "workflow", label: "workflow" },
  { id: "pipeline", label: "method" },
  { id: "tearsheets", label: "tearsheets" },
  { id: "tooling", label: "tooling" },
  { id: "start", label: "start" },
];
