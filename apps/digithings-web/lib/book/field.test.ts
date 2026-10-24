import { describe, expect, it } from "vitest";

import { fieldSvg } from "./field";

describe("book field", () => {
  it("renders a usable SVG field", () => {
    const svg = fieldSvg({ seed: 3319, time: 4200 });
    expect(svg).toContain("<svg");
    expect(svg).toContain("var(--ink)");
    expect(svg.length).toBeGreaterThan(1000);
  });

  it("draws different maps for different seeds", () => {
    expect(fieldSvg({ seed: 1, time: 4200 })).not.toBe(fieldSvg({ seed: 2, time: 4200 }));
  });
});
