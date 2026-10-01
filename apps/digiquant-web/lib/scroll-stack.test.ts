import { describe, expect, it } from "vitest";
import { runwayProgress, stageProgress } from "./scroll-stack";

describe("runwayProgress", () => {
  it("is 0 before the lead, 1 once the stage is about to unpin", () => {
    expect(runwayProgress(500, 2000, 800, 300)).toBe(0);
    expect(runwayProgress(300, 2000, 800, 300)).toBe(0);
    expect(runwayProgress(-1200, 2000, 800, 300)).toBe(1);
    expect(runwayProgress(-5000, 2000, 800, 300)).toBe(1);
  });

  it("moves forward as the runway scrolls up", () => {
    const a = runwayProgress(100, 2000, 800, 300);
    const b = runwayProgress(-400, 2000, 800, 300);
    expect(a).toBeGreaterThan(0);
    expect(b).toBeGreaterThan(a);
  });

  it("treats a runway no taller than the stage as already done", () => {
    expect(runwayProgress(0, 800, 800, 0)).toBe(1);
  });
});

describe("stageProgress", () => {
  it("starts every card hidden and ends every card settled", () => {
    for (let i = 0; i < 7; i++) {
      expect(stageProgress(0, i, 7)).toBe(0);
      expect(stageProgress(1, i, 7)).toBe(1);
    }
  });

  it("brings cards in order, left to right", () => {
    const at = [0, 1, 2, 3, 4, 5, 6].map((i) => stageProgress(0.45, i, 7));
    for (let i = 1; i < at.length; i++) expect(at[i - 1]).toBeGreaterThanOrEqual(at[i]);
    expect(at[0]).toBe(1);
    expect(at[6]).toBe(0);
  });
});
