import { describe, it, expect } from "vitest";
import { treemapAreas } from "@/lib/treemap";

const W = 1284;
const H = 1002;
const EPS = 1e-6;

function areas(weights: number[]) {
  return treemapAreas(weights, W, H).map((r) => r.w * r.h);
}

describe("treemapAreas", () => {
  it("returns one rect per weight and covers the box exactly", () => {
    const weights = [1, 0.84, 0.536, 0.426, 0.277, 0.207, 0.182, 0.162, 0.12, 0.06, 0.06];
    const rects = treemapAreas(weights, W, H);
    expect(rects).toHaveLength(weights.length);
    const total = areas(weights).reduce((acc, a) => acc + a, 0);
    expect(total).toBeCloseTo(W * H, 6);
  });

  it("keeps areas proportionate to the weights at every focus", () => {
    const base = [1, 0.84, 0.536, 0.426, 0.277, 0.207, 0.182, 0.162, 0.12, 0.06, 0.06];
    for (const focus of [-1, 0, 4, 8, 10]) {
      const weights = base.map((w, i) => (i === focus ? Math.max(w * 1.3, 0.5) : w));
      const got = areas(weights);
      const total = got.reduce((acc, a) => acc + a, 0);
      const wTotal = weights.reduce((acc, w) => acc + w, 0);
      weights.forEach((w, i) => {
        expect(got[i] / total).toBeCloseTo(w / wTotal, 6);
      });
    }
  });

  it("lays rects inside the box with no overlaps", () => {
    const weights = [1, 0.84, 0.536, 0.426, 0.277, 0.207, 0.182, 0.162, 0.12, 0.06, 0.06];
    const rects = treemapAreas(weights, W, H);
    rects.forEach((r) => {
      expect(r.x).toBeGreaterThanOrEqual(-EPS);
      expect(r.y).toBeGreaterThanOrEqual(-EPS);
      expect(r.x + r.w).toBeLessThanOrEqual(W + EPS);
      expect(r.y + r.h).toBeLessThanOrEqual(H + EPS);
      expect(r.w).toBeGreaterThan(0);
      expect(r.h).toBeGreaterThan(0);
    });
    for (let a = 0; a < rects.length; a++) {
      for (let b = a + 1; b < rects.length; b++) {
        const A = rects[a];
        const B = rects[b];
        const overlapX = Math.min(A.x + A.w, B.x + B.w) - Math.max(A.x, B.x);
        const overlapY = Math.min(A.y + A.h, B.y + B.h) - Math.max(A.y, B.y);
        expect(Math.min(overlapX, overlapY)).toBeLessThanOrEqual(EPS);
      }
    }
  });

  it("starts the first (largest) tile at the origin, so reading order is stable", () => {
    const rects = treemapAreas([1, 0.5, 0.25, 0.125], W, H);
    expect(rects[0].x).toBeCloseTo(0, 6);
    expect(rects[0].y).toBeCloseTo(0, 6);
  });

  it("fills the box with a single weight and returns [] for none", () => {
    expect(treemapAreas([3], W, H)).toEqual([{ x: 0, y: 0, w: W, h: H }]);
    expect(treemapAreas([], W, H)).toEqual([]);
  });
});
