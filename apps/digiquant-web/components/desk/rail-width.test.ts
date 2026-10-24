import { describe, expect, it } from "vitest";
import { RAIL_WIDTH_DEFAULT, RAIL_WIDTHS, stepRailWidth } from "./rail-width";

describe("rail width", () => {
  it("steps between the wide-layout sizes and stops at the ends", () => {
    expect(stepRailWidth(RAIL_WIDTH_DEFAULT, 1)).toBe(248);
    expect(stepRailWidth(RAIL_WIDTH_DEFAULT, -1)).toBe(160);
    expect(stepRailWidth(RAIL_WIDTHS[0], -1)).toBe(RAIL_WIDTHS[0]);
    expect(stepRailWidth(RAIL_WIDTHS[RAIL_WIDTHS.length - 1], 1)).toBe(RAIL_WIDTHS[RAIL_WIDTHS.length - 1]);
  });
});
