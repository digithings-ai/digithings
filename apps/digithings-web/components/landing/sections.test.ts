import { describe, expect, it } from "vitest";
import { LANDING_SECTIONS } from "./sections";

describe("landing sections", () => {
  it("keeps band ids unique", () => {
    const ids = LANDING_SECTIONS.map((section) => section.id);
    expect(new Set(ids).size).toBe(ids.length);
  });
});
