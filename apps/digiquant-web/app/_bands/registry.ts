/** Phase 0-owned, frozen shape: the ordered bands of the home page. page.tsx,
 *  SectionRail and the nav all read this list; passes edit only their own band
 *  file, never this one. */
export type BandId = "top" | "products" | "pipeline" | "tearsheets" | "strategy" | "dashboard" | "start";

export const BANDS: readonly { id: BandId; label: string }[] = [
  { id: "top", label: "top" },
  { id: "products", label: "products" },
  { id: "pipeline", label: "pipeline" },
  { id: "tearsheets", label: "tearsheets" },
  { id: "strategy", label: "strategy" },
  { id: "dashboard", label: "dashboard" },
  { id: "start", label: "start" },
];
