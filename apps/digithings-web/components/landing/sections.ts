/**
 * The landing page's bands, in page order. Feeds the gutter rail (`SectionRail`).
 */
export const LANDING_SECTIONS = [
  { id: "architecture", label: "stack" },
  { id: "why", label: "why" },
  { id: "open-source", label: "open-source" },
  { id: "digiquant", label: "digiquant" },
  { id: "pricing", label: "pricing" },
  { id: "faq", label: "faq" },
  { id: "contact", label: "contact" },
] as const;

export type LandingSectionId = (typeof LANDING_SECTIONS)[number]["id"];
