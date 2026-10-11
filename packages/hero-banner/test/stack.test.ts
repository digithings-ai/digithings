import { describe, expect, test } from "bun:test";

import { DIGIBASE } from "../src/definitions";
import { preparedBanner, sampleBanner } from "../src/engine";
import { litCells, pixelAt } from "../src/layout";
import type { StackState } from "../src/animations/stack";
import type { Frame } from "../src/types";

const { layout } = preparedBanner(DIGIBASE);
const state = preparedBanner(DIGIBASE).state as StackState;
const loadingMs = DIGIBASE.animation.loadingMs(state);
const tones = (f: Frame) => new Set(f.pixels.filter(Boolean).map((p) => p!.tone));
const at = (t: number, live = true) => sampleBanner(DIGIBASE, { t, live }).frame;

describe("digibase STACK", () => {
  test("records cover every lit cell exactly once, at most blockMax wide", () => {
    const seen = new Set<string>();
    for (const r of state.records) {
      expect(r.x1 - r.x0 + 1).toBeLessThanOrEqual(4);
      for (let x = r.x0; x <= r.x1; x += 1) {
        const key = `${x},${r.y}`;
        expect(seen.has(key)).toBe(false);
        seen.add(key);
      }
    }
    expect(seen.size).toBe(litCells(layout).length);
  });

  test("rows are written bottom-up and commit bottom-up", () => {
    const filled = state.commit.map((c, y) => [y, c] as const).filter(([, c]) => Number.isFinite(c));
    for (let i = 1; i < filled.length; i += 1) expect(filled[i][1]).toBeLessThan(filled[i - 1][1]);
    const firstStart = (y: number) => Math.min(...state.rows[y].map((i) => state.records[i].start));
    expect(firstStart(layout.height - 1)).toBeLessThan(firstStart(0));
  });

  test("a record never falls through a landed one", () => {
    for (const r of state.records) {
      for (const below of state.records) {
        if (below.y >= r.y || below.x1 < r.x0 || below.x0 > r.x1) continue;
        // `below` sits above `r` in the same columns: it must land after `r` has.
        expect(below.land).toBeGreaterThanOrEqual(r.land);
      }
    }
  });

  test("landed records are written (accent) until their row commits", () => {
    const y = layout.height - 1;
    const f = at(state.commit[y] - 1);
    for (const i of state.rows[y]) {
      const r = state.records[i];
      expect(pixelAt(f, r.x0, y)).toEqual({ tone: "accent", alpha: 1 });
    }
    expect(pixelAt(at(state.commit[y] + 10), state.records[state.rows[y][0]].x0, y)?.tone).toBe("glint");
  });

  test("LOADING ends on the settled word", () => {
    const end = at(loadingMs);
    for (const c of litCells(layout)) expect(pixelAt(end, c.x, c.y)).toEqual({ tone: "ink", alpha: 1 });
  });

  test("LIVE updates and scans, and keeps the word", () => {
    const seen = new Set<string>();
    for (let t = loadingMs; t < loadingMs + 30_000; t += 50) {
      const f = at(t);
      for (const tone of tones(f)) seen.add(tone);
      for (const c of litCells(layout)) expect(pixelAt(f, c.x, c.y)).not.toBeNull();
    }
    expect([...seen].sort()).toEqual(["accent", "glint", "ink"]);
  });

  test("frames are pure in time", () => {
    for (const t of [90, 777, 1500, loadingMs + 4321]) expect(at(t)).toEqual(at(t));
  });

  test("LIVE off settles on the plain word", () => {
    const f = at(loadingMs + 5000, false);
    expect([...tones(f)]).toEqual(["ink"]);
  });
});
