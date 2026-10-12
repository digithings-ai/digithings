import { describe, expect, test } from "bun:test";

import { DIGIBOOK } from "../src/definitions";
import { preparedBanner, sampleBanner } from "../src/engine";
import { litCells, pixelAt } from "../src/layout";
import { liveEvent, type PagesState } from "../src/animations/pages";
import type { Frame } from "../src/types";

const { layout } = preparedBanner(DIGIBOOK);
const state = preparedBanner(DIGIBOOK).state as PagesState;
const loadingMs = DIGIBOOK.animation.loadingMs(state);
const tones = (f: Frame) => new Set(f.pixels.filter(Boolean).map((p) => p!.tone));
const at = (t: number, live = true) => sampleBanner(DIGIBOOK, { t, live }).frame;
const count = (f: Frame) => f.pixels.filter(Boolean).length;

describe("digibook PAGES", () => {
  test("LOADING starts on a blank page", () => {
    expect(count(at(0))).toBe(0);
  });

  test("turns overlap like a riffle and the last is the slowest", () => {
    const { turns } = state;
    expect(turns.length).toBe(5);
    for (let i = 1; i < turns.length; i += 1) expect(turns[i].at).toBeLessThan(turns[i - 1].at + turns[i - 1].ms);
    expect(turns.at(-1)!.ms).toBe(Math.max(...turns.map((t) => t.ms)));
  });

  test("a turn in flight shows a fold (glint) and a flap (accent)", () => {
    const t = state.turns[0].at + state.turns[0].ms / 2;
    const seen = tones(at(t));
    expect(seen.has("glint")).toBe(true);
    expect(seen.has("accent")).toBe(true);
  });

  test("the fold leans: the bottom row leads the top", () => {
    const t = state.turns[0].at + state.turns[0].ms / 2;
    const f = at(t);
    const foldX = (y: number) => f.pixels.slice(y * f.width, (y + 1) * f.width).findIndex((p) => p?.tone === "glint");
    expect(foldX(layout.height - 1)).toBeLessThan(foldX(0));
  });

  test("each page carries more of the word than the one before", () => {
    // Sample just after each turn has fully landed (before the next uncovers more).
    const lit = state.turns.map((turn) => count(at(turn.at + turn.ms + 1)));
    for (let i = 1; i < lit.length; i += 1) expect(lit[i]).toBeGreaterThanOrEqual(lit[i - 1]);
  });

  test("LOADING ends on the settled word", () => {
    const end = at(loadingMs);
    for (const c of litCells(layout)) expect(pixelAt(end, c.x, c.y)).toEqual({ tone: "ink", alpha: 1 });
    expect(count(end)).toBe(litCells(layout).length);
  });

  test("LIVE turns pages both ways, riffles sometimes, and keeps the word", () => {
    const events = Array.from({ length: 60 }, (_, i) => liveEvent(state, i));
    expect(events.some((e) => e.length === 3)).toBe(true);
    expect(events.some((e) => e[0].back)).toBe(true);
    expect(events.some((e) => !e[0].back)).toBe(true);
    const seen = new Set<string>();
    for (let t = loadingMs; t < loadingMs + 40_000; t += 40) {
      const f = at(t);
      for (const tone of tones(f)) seen.add(tone);
      // Off the flap, the word is always there.
      for (const c of litCells(layout)) {
        const p = pixelAt(f, c.x, c.y);
        expect(p).not.toBeNull();
      }
    }
    expect([...seen].sort()).toEqual(["accent", "glint", "ink"]);
  });

  test("frames are pure in time", () => {
    for (const t of [90, 777, 1500, loadingMs + 4321]) expect(at(t)).toEqual(at(t));
  });

  test("LIVE off settles on the plain word", () => {
    expect([...tones(at(loadingMs + 5000, false))]).toEqual(["ink"]);
  });
});
