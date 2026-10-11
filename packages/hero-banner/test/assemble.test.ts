import { describe, expect, test } from "bun:test";

import type { AssembleState } from "../src/animations/assemble";
import { DIGITHINGS } from "../src/definitions";
import { preparedBanner, sampleBanner } from "../src/engine";
import { litCells, pixelAt } from "../src/layout";
import type { Frame } from "../src/types";

const { layout } = preparedBanner(DIGITHINGS);
const state = preparedBanner(DIGITHINGS).state as AssembleState;
const loadingMs = DIGITHINGS.animation.loadingMs(state);
const tones = (f: Frame) => new Set(f.pixels.filter(Boolean).map((p) => p!.tone));
const at = (t: number, live = true) => sampleBanner(DIGITHINGS, { t, live }).frame;

describe("digithings ASSEMBLE", () => {
  test("one part per lit cell, starting inside the frame", () => {
    expect(state.parts.length).toBe(litCells(layout).length);
    for (const p of state.parts) {
      expect(p.sx).toBeGreaterThanOrEqual(0);
      expect(p.sx).toBeLessThan(layout.width);
      expect(p.sy).toBeGreaterThanOrEqual(0);
      expect(p.sy).toBeLessThan(layout.height);
      expect(p.land).toBeGreaterThan(p.launch);
    }
  });

  test("letters assemble left to right", () => {
    for (let g = 1; g < state.socketAt.length; g += 1) expect(state.socketAt[g]).toBeGreaterThan(state.socketAt[g - 1]!);
  });

  test("nothing shows before the first launch; LOADING ends on the settled word", () => {
    expect(at(0).pixels.every((p) => p === null)).toBe(true);
    const end = at(loadingMs);
    for (const c of litCells(layout)) expect(pixelAt(end, c.x, c.y)).toEqual({ tone: "ink", alpha: 1 });
    expect([...tones(end)]).toEqual(["ink"]);
  });

  test("a part flies in the accent and seats with an accent flash", () => {
    const p = state.parts[0]!;
    const mid = at((p.launch + p.land) / 2);
    expect(mid.pixels.some((px) => px?.tone === "accent")).toBe(true);
    expect(pixelAt(at(p.land + 1), p.x, p.y)).toEqual({ tone: "accent", alpha: 1 });
    expect(pixelAt(at(p.land + DIGITHINGS.animation.liveTickMs * 10), p.x, p.y)).toEqual({ tone: "ink", alpha: 1 });
  });

  test("LIVE lifts parts and keeps every socket visible", () => {
    let lifted = 0;
    for (let t = loadingMs; t < loadingMs + 30_000; t += 50) {
      const f = at(t);
      for (const c of litCells(layout)) expect(pixelAt(f, c.x, c.y)).not.toBeNull();
      if (tones(f).has("accent")) lifted += 1;
    }
    expect(lifted).toBeGreaterThan(30_000 / 50 / 4);
  });

  test("frames are pure in time", () => {
    for (const t of [90, 777, 1500, loadingMs + 4321]) expect(at(t)).toEqual(at(t));
  });

  test("LIVE off and reduced motion settle on the plain word", () => {
    expect([...tones(at(loadingMs + 5000, false))]).toEqual(["ink"]);
    expect([...tones(sampleBanner(DIGITHINGS, { t: 300, motion: "reduced" }).frame)]).toEqual(["ink"]);
  });
});
