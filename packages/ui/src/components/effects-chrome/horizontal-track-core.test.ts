import { describe, expect, it } from "vitest";
import {
  clamp,
  focusTargetX,
  nearestIndex,
  runwayHeight,
  scrollTopForX,
  trackTravel,
} from "./horizontal-track-core";

describe("horizontal track geometry", () => {
  it("derives travel from content width and never goes negative", () => {
    expect(trackTravel(2400, 1000)).toBe(1400);
    expect(trackTravel(800, 1000)).toBe(0);
  });

  it("derives the runway from the pin height plus travel (1px : 1px)", () => {
    expect(runwayHeight(700, 1400)).toBe(2100);
    expect(runwayHeight(700.4, 0)).toBe(700);
  });

  it("picks the item whose leading edge is nearest the travel", () => {
    const offsets = [0, 300, 620, 940];
    expect(nearestIndex(offsets, 0)).toBe(0);
    expect(nearestIndex(offsets, 170)).toBe(1);
    expect(nearestIndex(offsets, 900)).toBe(3);
    expect(nearestIndex([], 50)).toBe(0);
  });

  it("scrolls to a focused off-screen card and leaves visible ones alone", () => {
    const base = { itemWidth: 300, viewportWidth: 1000, travel: 1400 };
    expect(focusTargetX({ ...base, itemLeft: 100, currentX: 0 })).toBeNull();
    expect(focusTargetX({ ...base, itemLeft: 1200, currentX: 0 })).toBe(1200);
    // clamped to the end of the runway
    expect(focusTargetX({ ...base, itemLeft: 1900, currentX: 0 })).toBe(1400);
    // a card scrolled off the leading edge is brought back
    expect(focusTargetX({ ...base, itemLeft: 100, currentX: 600 })).toBe(100);
  });

  it("maps travel to a document scrollTop 1px : 1px, clamped", () => {
    const a = { runwayTopInDocument: 2000, pinTop: 64, travel: 1400 };
    expect(scrollTopForX({ ...a, x: 0 })).toBe(1936);
    expect(scrollTopForX({ ...a, x: 500 })).toBe(2436);
    expect(scrollTopForX({ ...a, x: 9999 })).toBe(3336);
    expect(clamp(-5, 0, 10)).toBe(0);
  });
});
