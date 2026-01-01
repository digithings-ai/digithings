import { describe, expect, test } from "bun:test";

import { DIGIVOICE, DIGIVOICE_VARIANTS } from "../src/definitions";
import { preparedBanner, sampleBanner } from "../src/engine";
import { litCells, pixelAt } from "../src/layout";
import { speechLevel, type SpeakState } from "../src/animations/speak";
import type { BannerDefinition, Frame } from "../src/types";

const { layout } = preparedBanner(DIGIVOICE);
const state = preparedBanner(DIGIVOICE).state as SpeakState;
const loadingMs = DIGIVOICE.animation.loadingMs(state);
const tones = (f: Frame) => new Set(f.pixels.filter(Boolean).map((p) => p!.tone));
const at = (t: number, live = true, def: BannerDefinition = DIGIVOICE) => sampleBanner(def, { t, live }).frame;
const full = (f: Frame) => litCells(layout).filter((c) => pixelAt(f, c.x, c.y)?.alpha === 1).length;

describe("digivoice SPEAK", () => {
  test("LOADING: the faint word, then a left-to-right sweep fills it", () => {
    expect(full(at(state.options.startMs))).toBe(0);
    const f = at(state.options.startMs + state.options.sweepMs / 2);
    const xs = litCells(layout).filter((c) => pixelAt(f, c.x, c.y)?.alpha === 1).map((c) => c.x);
    expect(Math.max(...xs)).toBeLessThan(layout.width * 0.7);
    expect(tones(f).has("accent")).toBe(true);
  });

  test("LOADING ends on the settled word, which is the still", () => {
    const end = at(loadingMs - 1);
    for (const c of litCells(layout)) expect(pixelAt(end, c.x, c.y)).toEqual({ tone: "ink", alpha: 1 });
    expect(sampleBanner(DIGIVOICE, { t: 0, motion: "reduced" }).frame).toEqual(end);
  });

  test("LIVE starts from the full word, then speaks with caps, and the word always shows", () => {
    expect(full(at(loadingMs))).toBe(litCells(layout).length);
    const seen = new Set<string>();
    for (let t = loadingMs; t < loadingMs + 20_000; t += 50) {
      const f = at(t);
      for (const tone of tones(f)) seen.add(tone);
      for (const c of litCells(layout)) expect(pixelAt(f, c.x, c.y)).not.toBeNull();
    }
    expect([...seen].sort()).toEqual(["accent", "ink"]);
  });

  test("speech pauses: the level drops to the floor between phrases", () => {
    const levels = Array.from({ length: Math.ceil(state.cycleMs / 10) }, (_, i) => speechLevel(state, i * 10, 0.5));
    expect(Math.min(...levels)).toBe(state.options.floor);
    expect(Math.max(...levels)).toBeGreaterThan(0.6);
    expect(speechLevel(state, 1234, 0.3)).toBe(speechLevel(state, 1234 + state.cycleMs, 0.3));
  });

  test("the variations differ from the locked banner in LIVE only", () => {
    for (const def of Object.values(DIGIVOICE_VARIANTS)) {
      expect(at(500, true, def)).toEqual(at(500));
      expect(at(loadingMs + 2000, true, def)).not.toEqual(at(loadingMs + 2000));
    }
  });

  test("frames are pure in time", () => {
    for (const t of [90, 777, loadingMs + 4321]) expect(at(t)).toEqual(at(t));
  });

  test("LIVE off settles on the plain word", () => {
    expect([...tones(at(loadingMs + 5000, false))]).toEqual(["ink"]);
  });
});
