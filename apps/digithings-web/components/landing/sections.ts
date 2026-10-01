/**
 * The landing page's bands, in page order. One list feeds the gutter rail
 * (`SectionRail`) and the `NN / label` eyebrow on each band's heading
 * (`SectionHead`), so the number a reader sees on the band is the number the
 * rail showed them on the way down.
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

export const pad2 = (n: number) => String(n).padStart(2, "0");

/** `03 / open-source` for a band id. */
export function sectionEyebrow(id: LandingSectionId): string {
  const index = LANDING_SECTIONS.findIndex((section) => section.id === id);
  const section = LANDING_SECTIONS[index];
  return `${pad2(index + 1)} / ${section?.label ?? id}`;
}
