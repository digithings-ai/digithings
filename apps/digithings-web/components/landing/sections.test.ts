import { describe, expect, it } from "vitest";
import { LANDING_SECTIONS, pad2, sectionEyebrow } from "./sections";

describe("landing sections", () => {
  it("numbers each band by its place in the rail", () => {
    expect(sectionEyebrow("architecture")).toBe("01 / stack");
    expect(sectionEyebrow("open-source")).toBe("03 / open-source");
    expect(sectionEyebrow("contact")).toBe(`${pad2(LANDING_SECTIONS.length)} / contact`);
  });

  it("keeps band ids unique", () => {
    const ids = LANDING_SECTIONS.map((section) => section.id);
    expect(new Set(ids).size).toBe(ids.length);
  });
});
