import { describe, expect, test } from "bun:test";

import { DIGIKEY } from "../src/definitions";
import { preparedBanner, sampleBanner } from "../src/engine";
import { litCells, pixelAt } from "../src/layout";
import type { TumblerState } from "../src/animations/tumbler";
import type { Frame } from "../src/types";

const { layout } = preparedBanner(DIGIKEY);
const state = preparedBanner(DIGIKEY).state as TumblerState;
const loadingMs = DIGIKEY.animation.loadingMs(state);
const tones = (f: Frame) => new Set(f.pixels.filter(Boolean).map((p) => p!.tone));
const at = (t: number, live = true) => sampleBanner(DIGIKEY, { t, live }).frame;

describe("digikey TUMBLER", () => {
  test("every pin starts out of line", () => {
    for (const x of state.columns.keys()) if (state.columns[x]!.length) expect(state.offset[x]).not.toBe(0);
  });

  test("pins left of the key tip are set, pins right of it are locked and dim", () => {
    const f = at(state.options.keyMs * 0.5);
    const firstCol = litCells(layout).filter((c) => c.x === 0);
    for (const c of firstCol) expect(pixelAt(f, c.x, c.y)?.tone).toBe("ink");
    const last = layout.width - 1;
    const dim = f.pixels.filter((p, i) => i % f.width >= last - 3 && p?.tone === "ink");
    expect(dim.length).toBeGreaterThan(0);
    for (const p of dim) expect(p!.alpha).toBe(state.options.locked);
  });

  test("the key blade runs along the shear line while it slides in", () => {
    const f = at(state.options.keyMs * 0.4);
    const blade = Array.from({ length: f.width }, (_, x) => pixelAt(f, x, state.shear)).filter((p) => p?.tone === "accent");
    expect(blade.length).toBeGreaterThan(3);
  });

  test("the turn rolls a glint band down the word, then it settles as ink", () => {
    const f = at(state.turnStartMs + state.options.turnMs / 2);
    expect(tones(f).has("glint")).toBe(true);
    const end = at(loadingMs - 1);
    for (const c of litCells(layout)) expect(pixelAt(end, c.x, c.y)).not.toBeNull();
    const after = at(loadingMs + 1, false);
    for (const c of litCells(layout)) expect(pixelAt(after, c.x, c.y)).toEqual({ tone: "ink", alpha: 1 });
  });

  test("LIVE picks letters and turns the key, and the word comes back each time", () => {
    const seen = new Set<string>();
    for (let t = loadingMs; t < loadingMs + 30_000; t += 50) for (const tone of tones(at(t))) seen.add(tone);
    expect([...seen].sort()).toEqual(["accent", "glint", "ink"]);
  });

  test("frames are pure in time", () => {
    for (const t of [90, 777, 1500, loadingMs + 4321]) expect(at(t)).toEqual(at(t));
  });

  test("LIVE off settles on the plain word", () => {
    expect([...tones(at(loadingMs + 5000, false))]).toEqual(["ink"]);
  });
});
