import { describe, expect, it } from "vitest";
import { CONTRAST_MINIMUM, contrast, luminance } from "./devkit-contrast";

describe("devkit contrast helpers", () => {
  it("pins the WCAG AA text threshold", () => {
    expect(CONTRAST_MINIMUM).toBe(4.5);
  });
  it("scores black-on-white near 21:1", () => {
    expect(contrast("#000000", "#ffffff")).toBeCloseTo(21, 0);
  });
  it("scores identical colors at 1:1", () => {
    expect(contrast("#e2708a", "#e2708a")).toBe(1);
  });
  it("linearizes sRGB per WCAG 2", () => {
    expect(luminance([255, 255, 255])).toBeCloseTo(1, 3);
    expect(luminance([0, 0, 0])).toBe(0);
  });
});
