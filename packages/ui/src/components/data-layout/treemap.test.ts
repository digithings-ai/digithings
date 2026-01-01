import { describe, it, expect } from "vitest";
import { treemapAnchored, treemapAreas, treemapAreasConstrained } from "./treemap";

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

describe("treemapAreasConstrained", () => {
  const weights = [1, 0.84, 0.536, 0.426, 0.277, 0.207, 0.182, 0.162, 0.12, 0.06, 0.06];

  it("lifts narrow tiles to their minimum width when the box allows it", () => {
    const mins = weights.map(() => ({ minW: 176, minH: 84 }));
    const rects = treemapAreasConstrained(weights, W, H, mins);
    expect(rects).toHaveLength(weights.length);
    rects.forEach((r) => {
      expect(r.w).toBeGreaterThanOrEqual(176 - 1);
      expect(r.h).toBeGreaterThanOrEqual(84 - 1);
    });
    const total = rects.reduce((acc, r) => acc + r.w * r.h, 0);
    expect(total).toBeCloseTo(W * H, 4);
  });

  it("guarantees a focused tile's content minimum", () => {
    const mins = weights.map((_, i) =>
      i === 10 ? { minW: 300, minH: 260 } : { minW: 176, minH: 84 },
    );
    const boosted = weights.map((w, i) => (i === 10 ? Math.max(w * 1.3, 0.5) : w));
    const rects = treemapAreasConstrained(boosted, W, H, mins);
    expect(rects[10].w).toBeGreaterThanOrEqual(300 - 1);
    expect(rects[10].h).toBeGreaterThanOrEqual(260 - 1);
  });

  it("holds every minimum jointly in a narrow box with a large focused tile", () => {
    // Live regression (1000px viewport): a 368x776 focused tile starved a
    // roadmap tile to 101px wide against its 184px minimum — the iterative
    // chase froze their ratios instead of satisfying both.
    const NW = 1000;
    const NH = 784;
    const boosted = weights.map((w, i) => (i === 3 ? Math.max(w * 1.3, 0.5) : w));
    const mins = weights.map((_, i) =>
      i === 3 ? { minW: 308, minH: 383 } : { minW: 184, minH: 92 },
    );
    const rects = treemapAreasConstrained(boosted, NW, NH, mins);
    expect(rects).toHaveLength(weights.length);
    rects.forEach((r) => {
      expect(r.w).toBeGreaterThanOrEqual(184 - 1);
      expect(r.h).toBeGreaterThanOrEqual(92 - 1);
    });
    expect(rects[3].w).toBeGreaterThanOrEqual(308 - 1);
    expect(rects[3].h).toBeGreaterThanOrEqual(383 - 1);
    const total = rects.reduce((acc, r) => acc + r.w * r.h, 0);
    expect(total).toBeCloseTo(NW * NH, 4);
  });

  it("packs sane aspects when boosts invert the LOC order", () => {
    // needExtra top-ups can make a late (small) tile outweigh digiquant.
    // Without a descending sort per solve, squarified degrades into slivers.
    const skewed = [1, 0.84, 0.536, 0.426, 0.277, 0.207, 0.182, 0.162, 0.12, 2.1, 1.4];
    const total = skewed.reduce((acc, w) => acc + w, 0);
    const loose = skewed.map(() => ({ minW: 1, minH: 1 }));
    treemapAreasConstrained(skewed, W, H, loose).forEach((r, i) => {
      expect((r.w * r.h) / (W * H)).toBeCloseTo(skewed[i] / total, 6);
    });
    const tight = skewed.map(() => ({ minW: 184, minH: 92 }));
    treemapAreasConstrained(skewed, W, H, tight).forEach((r) => {
      expect(Math.max(r.w / r.h, r.h / r.w)).toBeLessThan(4);
    });
  });

  it("matches the pure solve when nothing violates, and terminates best-effort when the box cannot fit", () => {    const loose = weights.map(() => ({ minW: 1, minH: 1 }));
    expect(treemapAreasConstrained(weights, W, H, loose)).toEqual(treemapAreas(weights, W, H));
    const impossible = weights.map(() => ({ minW: 5000, minH: 5000 }));
    const rects = treemapAreasConstrained(weights, W, H, impossible, 3);
    expect(rects).toHaveLength(weights.length);
    rects.forEach((r) => {
      expect(Number.isFinite(r.x + r.y + r.w + r.h)).toBe(true);
      expect(r.w).toBeGreaterThan(0);
      expect(r.h).toBeGreaterThan(0);
    });
  });
});

describe("treemapAnchored", () => {
  const weights = [1, 0.84, 0.536, 0.426, 0.277, 0.207, 0.182, 0.162, 0.12, 0.06, 0.06];
  const restMins = weights.map(() => ({ minW: 158, minH: 92 }));
  const rest = treemapAreasConstrained(weights, W, H, restMins);

  function anchored(focus: number, bw = W, bh = H) {
    const mins = weights.map((_, i) =>
      i === focus ? { minW: 308, minH: 268 } : { minW: 158, minH: 92 },
    );
    const boosted = weights.map((w, i) => (i === focus ? Math.max(w * 1.3, 0.5) : w));
    const grown = treemapAreasConstrained(boosted, bw, bh, mins);
    return treemapAnchored(boosted, bw, bh, mins, rest, focus, {
      w: grown[focus].w,
      h: grown[focus].h,
    });
  }

  it("keeps the focused tile on its rest top-left while meeting its minimum", () => {
    for (const focus of [0, 3, 7, 10]) {
      const rects = anchored(focus);
      expect(rects[focus].x).toBeCloseTo(
        Math.min(rest[focus].x, W - rects[focus].w),
        6,
      );
      expect(rects[focus].y).toBeCloseTo(
        Math.min(rest[focus].y, H - rects[focus].h),
        6,
      );
      expect(rects[focus].w).toBeGreaterThanOrEqual(308 - 1);
      expect(rects[focus].h).toBeGreaterThanOrEqual(268 - 1);
    }
  });

  it("stays a full partition with no overlaps and no escapes", () => {
    for (const focus of [0, 5, 10]) {
      const rects = anchored(focus);
      expect(rects).toHaveLength(weights.length);
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
      const total = rects.reduce((acc, r) => acc + r.w * r.h, 0);
      expect(total).toBeCloseTo(W * H, 4);
    }
  });

  it("holds up in a narrow box with a large focused tile", () => {
    const NW = 1000;
    const NH = 784;
    const narrowRest = treemapAreasConstrained(weights, NW, NH, restMins);
    const mins = weights.map((_, i) =>
      i === 3 ? { minW: 308, minH: 383 } : { minW: 158, minH: 92 },
    );
    const boosted = weights.map((w, i) => (i === 3 ? Math.max(w * 1.3, 0.5) : w));
    const grown = treemapAreasConstrained(boosted, NW, NH, mins);
    const rects = treemapAnchored(boosted, NW, NH, mins, narrowRest, 3, {
      w: grown[3].w,
      h: grown[3].h,
    });
    expect(rects[3].x).toBeCloseTo(Math.min(narrowRest[3].x, NW - rects[3].w), 6);
    expect(rects[3].y).toBeCloseTo(Math.min(narrowRest[3].y, NH - rects[3].h), 6);
    rects.forEach((r) => {
      expect(r.x + r.w).toBeLessThanOrEqual(NW + EPS);
      expect(r.y + r.h).toBeLessThanOrEqual(NH + EPS);
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

  it("keeps a side tile at its minimum when the focused tile would otherwise leave a sliver", () => {
    const NW = 1100;
    const NH = 700;
    const tileMins = weights.map(() => ({ minW: 184, minH: 100 }));
    const layout = treemapAreasConstrained(weights, NW, NH, tileMins);
    const rects = treemapAnchored(weights, NW, NH, tileMins, layout, 0, { w: 900, h: 520 });
    expect(rects).toHaveLength(weights.length);
    rects.forEach((r, i) => {
      expect(r.w).toBeGreaterThanOrEqual(tileMins[i].minW - 1);
      expect(r.h).toBeGreaterThanOrEqual(tileMins[i].minH - 1);
      expect(r.x).toBeGreaterThanOrEqual(-EPS);
      expect(r.y).toBeGreaterThanOrEqual(-EPS);
      expect(r.x + r.w).toBeLessThanOrEqual(NW + EPS);
      expect(r.y + r.h).toBeLessThanOrEqual(NH + EPS);
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
    const total = rects.reduce((acc, r) => acc + r.w * r.h, 0);
    expect(total).toBeCloseTo(NW * NH, 4);
  });
});
