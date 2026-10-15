import { describe, expect, it } from "vitest";

import { HEADLINE_CORE, blobClearance, leftShare, parseSeed, planMap } from "./embedding-map";

const FRAMES = [
  { name: "desktop", aspect: 1440 / 480, small: false },
  { name: "mobile", aspect: 390 / 640, small: true },
] as const;
const SEEDS = Array.from({ length: 300 }, (_, n) => n * 7919 + 1);

describe("embedding map plan", () => {
  it("is deterministic per seed", () => {
    expect(planMap(4242, 3, false)).toEqual(planMap(4242, 3, false));
    expect(planMap(4242, 3, false)).not.toEqual(planMap(4243, 3, false));
  });

  for (const frame of FRAMES) {
    describe(frame.name, () => {
      const plans = SEEDS.map((seed) => planMap(seed, frame.aspect, frame.small));

      it("keeps every cluster out from under the headline", () => {
        for (const plan of plans) {
          for (const c of plan.clusters) {
            for (const b of c.blobs) expect(blobClearance(b, frame.aspect, frame.small)).toBeGreaterThanOrEqual(HEADLINE_CORE);
          }
        }
      });

      it("balances land mass left and right", () => {
        const shares = plans.map((p) => leftShare(p.clusters, frame.aspect));
        // The rare seed that can't balance stays within a loose bound; most land near the middle.
        for (const s of shares) expect(Math.abs(s - 0.5)).toBeLessThan(0.3);
        expect(shares.filter((s) => Math.abs(s - 0.5) <= 0.15).length / shares.length).toBeGreaterThan(0.9);
      });

      it("varies the cluster count, within a sane range", () => {
        const counts = new Set(plans.map((p) => p.clusters.length));
        expect(counts.size).toBeGreaterThan(3);
        for (const p of plans) {
          expect(p.clusters.length).toBeGreaterThanOrEqual(2);
          expect(p.clusters.length).toBeLessThanOrEqual(frame.small ? 7 : 12);
        }
      });
    });
  }
});

describe("parseSeed", () => {
  it("uses digits as-is, hashes other text, ignores blanks", () => {
    expect(parseSeed("42")).toBe(42);
    expect(parseSeed(" 42 ")).toBe(42);
    expect(parseSeed("launch")).toBe(parseSeed("launch"));
    expect(parseSeed("launch")).not.toBe(parseSeed("launch2"));
    expect(parseSeed("")).toBeNull();
    expect(parseSeed(null)).toBeNull();
  });
});
