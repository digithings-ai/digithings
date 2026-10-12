import { describe, expect, test } from "bun:test";

import { DIGIGRAPH } from "../src/definitions";
import { preparedBanner, sampleBanner } from "../src/engine";
import { litCells, pixelAt } from "../src/layout";
import type { TraverseState } from "../src/animations/traverse";
import type { Frame } from "../src/types";

const { layout } = preparedBanner(DIGIGRAPH);
const state = preparedBanner(DIGIGRAPH).state as TraverseState;
const loadingMs = DIGIGRAPH.animation.loadingMs(state);
const tones = (f: Frame) => new Set(f.pixels.filter(Boolean).map((p) => p!.tone));
const at = (t: number, live = true) => sampleBanner(DIGIGRAPH, { t, live }).frame;

describe("digigraph TRAVERSE", () => {
  test("the walk reaches every lit pixel, and every letter has tasks", () => {
    expect(state.cells.length).toBe(litCells(layout).length);
    for (let g = 0; g < state.glyphs; g += 1) expect(state.cells.some((c) => c.glyph === g && c.task)).toBe(true);
  });

  test("before the run starts the graph is a blueprint: dim strokes, dim accent tasks", () => {
    const f = at(0);
    for (const c of state.cells) {
      const p = pixelAt(f, c.x, c.y)!;
      expect(p.alpha).toBeLessThan(1);
      expect(p.tone).toBe(c.task ? "accent" : "ink");
    }
  });

  test("the run floods the first letter before the last, with an accent front", () => {
    const f = at(state.options.startMs + state.exitDist[0]! * state.options.stepMs);
    expect(tones(f).has("accent")).toBe(true);
    const last = state.cells.filter((c) => c.glyph === state.glyphs - 1);
    for (const c of last) expect(pixelAt(f, c.x, c.y)!.alpha).toBeLessThan(1);
  });

  test("hop edges are drawn in the gaps while the graph runs, and gone once it settles", () => {
    const f = at(loadingMs - state.options.holdMs - 1);
    const hop = state.hops[0]![0]!;
    expect(pixelAt(f, hop.x, hop.y)?.tone).toBe("accent");
    const end = at(loadingMs + 1, false);
    for (const path of state.hops) for (const p of path) expect(pixelAt(end, p.x, p.y)).toBeNull();
  });

  test("tasks glint as the run reaches them, then the word settles as ink", () => {
    const seen = new Set<string>();
    for (let t = 0; t < loadingMs; t += 20) for (const tone of tones(at(t))) seen.add(tone);
    expect(seen.has("glint")).toBe(true);
    for (const c of litCells(layout)) expect(pixelAt(at(loadingMs + 1, false), c.x, c.y)).toEqual({ tone: "ink", alpha: 1 });
  });

  test("LIVE runs walk the graph, and the word comes back between runs", () => {
    const seen = new Set<string>();
    let plain = 0;
    for (let t = loadingMs; t < loadingMs + 30_000; t += 40) {
      const ts = tones(at(t));
      for (const tone of ts) seen.add(tone);
      if (ts.size === 1) plain += 1;
    }
    expect([...seen].sort()).toEqual(["accent", "glint", "ink"]);
    expect(plain).toBeGreaterThan(0);
  });

  test("frames are pure in time", () => {
    for (const t of [90, 777, 1500, loadingMs + 4321]) expect(at(t)).toEqual(at(t));
  });

  test("LIVE off and reduced motion settle on the plain word", () => {
    expect([...tones(at(loadingMs + 5000, false))]).toEqual(["ink"]);
    expect([...tones(sampleBanner(DIGIGRAPH, { t: 300, motion: "reduced" }).frame)]).toEqual(["ink"]);
  });
});
