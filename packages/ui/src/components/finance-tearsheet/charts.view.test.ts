import { describe, expect, it } from "vitest";
import { MIN_VIEW, clampView } from "./charts";

/**
 * Regression for #1180 — legacy digiquant-web ComboPnl could blank when the
 * shared zoom window collapsed. The promoted finance-tearsheet grammar clamps
 * every wheel/pan update through `clampView`.
 */
describe("clampView", () => {
  it("passes through a healthy window unchanged", () => {
    expect(clampView(0.1, 0.9)).toEqual({ lo: 0.1, hi: 0.9 });
  });

  it("expands an empty window (lo === hi) to MIN_VIEW", () => {
    const v = clampView(0.5, 0.5);
    expect(v.hi - v.lo).toBeGreaterThanOrEqual(MIN_VIEW - 1e-12);
    expect(v.lo).toBeGreaterThanOrEqual(0);
    expect(v.hi).toBeLessThanOrEqual(1);
  });

  it("expands an inverted window (lo > hi) into a valid MIN_VIEW span", () => {
    const v = clampView(0.8, 0.2);
    expect(v.hi).toBeGreaterThan(v.lo);
    expect(v.hi - v.lo).toBeGreaterThanOrEqual(MIN_VIEW - 1e-12);
  });

  it("clamps out-of-range endpoints into [0, 1]", () => {
    expect(clampView(-0.5, 1.5)).toEqual({ lo: 0, hi: 1 });
  });

  it("keeps a near-zero empty window recoverable at the left edge", () => {
    const v = clampView(0, 0);
    expect(v).toEqual({ lo: 0, hi: MIN_VIEW });
  });

  it("keeps a near-one empty window recoverable at the right edge", () => {
    const v = clampView(1, 1);
    expect(v).toEqual({ lo: 1 - MIN_VIEW, hi: 1 });
  });
});
