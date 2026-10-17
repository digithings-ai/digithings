import { describe, expect, test } from "bun:test";

import { DIGISEARCH } from "../src/definitions";
import { preparedBanner, sampleBanner } from "../src/engine";
import { litCells, pixelAt } from "../src/layout";
import { liveQuery, matches, type ScanState } from "../src/animations/scan";
import type { Frame } from "../src/types";

const { layout } = preparedBanner(DIGISEARCH);
const state = preparedBanner(DIGISEARCH).state as ScanState;
const loadingMs = DIGISEARCH.animation.loadingMs(state);
const tones = (f: Frame) => new Set(f.pixels.filter(Boolean).map((p) => p!.tone));
const at = (t: number, live = true) => sampleBanner(DIGISEARCH, { t, live }).frame;
const word = litCells(layout);

describe("digisearch SCAN", () => {
  test("LOADING starts with the word hidden in the index", () => {
    const f = at(0);
    expect([...tones(f)]).toEqual(["accent"]);
    // Every word cell is there, but no brighter than the decoys around it.
    for (const c of word) expect(pixelAt(f, c.x, c.y)!.tone).toBe("accent");
    const decoys = f.pixels.filter(Boolean).length - word.length;
    expect(decoys).toBeGreaterThan(word.length / 3);
  });

  test("mid-sweep: hits behind the beam, the index ahead of it", () => {
    const f = at(loadingMs / 2);
    expect(tones(f).has("glint")).toBe(true);
    const beamX = f.pixels.findIndex((p) => p?.tone === "glint") % f.width;
    const left = word.filter((c) => c.x < beamX - 1 && c.x >= beamX - state.options.trail);
    expect(left.length).toBeGreaterThan(0);
    for (const c of left) expect(pixelAt(f, c.x, c.y)).toEqual({ tone: "accent", alpha: 1 });
    const ahead = word.filter((c) => c.x > beamX + 1);
    for (const c of ahead) expect(pixelAt(f, c.x, c.y)!.alpha).toBeLessThan(0.5);
  });

  test("LOADING ends on the settled word", () => {
    const end = at(loadingMs);
    for (const c of word) expect(pixelAt(end, c.x, c.y)).toEqual({ tone: "ink", alpha: 1 });
    expect(end.pixels.filter(Boolean).length).toBe(word.length);
  });

  test("matches covers every occurrence", () => {
    expect(matches("DIGISEARCH", "I")).toEqual([false, true, false, true, false, false, false, false, false, false]);
    expect(matches("DIGISEARCH", "SEARCH").filter(Boolean).length).toBe(6);
  });

  test("the first query is SEARCH; later ones are substrings of the word", () => {
    expect(liveQuery(state, 0).text).toBe("SEARCH");
    for (let i = 1; i < 40; i += 1) {
      const q = liveQuery(state, i);
      expect("DIGISEARCH".includes(q.text)).toBe(true);
      expect(q.hits.some(Boolean)).toBe(true);
    }
  });

  test("LIVE highlights hits, dims the rest, then clears", () => {
    const q = liveQuery(state, 0);
    const { liveSweepMs, holdMs, fadeMs } = state.options;
    const f = at(loadingMs + q.at + liveSweepMs + holdMs / 2);
    for (const c of word) {
      const p = pixelAt(f, c.x, c.y)!;
      if (q.hits[c.glyph]) expect(p).toEqual({ tone: "accent", alpha: 1 });
      else expect(p.alpha).toBeLessThan(1);
    }
    const after = at(loadingMs + q.at + liveSweepMs + holdMs + fadeMs + 1);
    expect([...tones(after)]).toEqual(["ink"]);
  });

  test("LIVE never loses the word", () => {
    for (let t = loadingMs; t < loadingMs + 30_000; t += 40) {
      const f = at(t);
      for (const c of word) expect(pixelAt(f, c.x, c.y)).not.toBeNull();
    }
  });

  test("frames are pure in time", () => {
    for (const t of [90, 777, 1500, loadingMs + 4321]) expect(at(t)).toEqual(at(t));
  });

  test("LIVE off settles on the plain word", () => {
    expect([...tones(at(loadingMs + 7000, false))]).toEqual(["ink"]);
  });
});
