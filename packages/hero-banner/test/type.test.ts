import { describe, expect, test } from "bun:test";

import { DIGIDEV } from "../src/definitions";
import { preparedBanner, sampleBanner } from "../src/engine";
import { litCells, pixelAt } from "../src/layout";
import { liveEvent, type TypeState } from "../src/animations/type";
import type { Frame } from "../src/types";

const { layout } = preparedBanner(DIGIDEV);
const state = preparedBanner(DIGIDEV).state as TypeState;
const loadingMs = DIGIDEV.animation.loadingMs(state);
const tones = (f: Frame) => new Set(f.pixels.filter(Boolean).map((p) => p!.tone));
const at = (t: number, live = true) => sampleBanner(DIGIDEV, { t, live }).frame;
const count = (f: Frame) => f.pixels.filter(Boolean).length;
const block = DIGIDEV.font.cols * DIGIDEV.font.rows;

describe("digidev TYPE", () => {
  test("LOADING opens on a lone block cursor", () => {
    expect(count(at(0))).toBe(block);
    expect([...tones(at(0))]).toEqual(["accent"]);
  });

  test("one typo is typed, backspaced and retyped", () => {
    const backspaces = state.keys.filter((k) => k.char === null);
    expect(backspaces.length).toBe(1);
    const slot = backspaces[0].slot;
    const onSlot = state.keys.filter((k) => k.slot === slot);
    expect(onSlot.map((k) => k.char === layout.text[slot])).toEqual([false, false, true]);
  });

  test("keystrokes are uneven and in order", () => {
    const gaps = state.keys.slice(1).map((k, i) => k.at - state.keys[i].at);
    for (const g of gaps) expect(g).toBeGreaterThan(0);
    expect(new Set(gaps).size).toBeGreaterThan(2);
  });

  test("the cursor shows the glyph under it in inverse video", () => {
    // Parked on the last glyph, blink on: block minus the glyph cells.
    const t = state.typedAt + 1;
    const last = litCells(layout).filter((c) => c.glyph === layout.text.length - 1);
    const f = at(t);
    for (const c of last) expect(pixelAt(f, c.x, c.y)).toBeNull();
    const x0 = layout.starts[layout.text.length - 1];
    const lit = Array.from({ length: layout.height }, (_, y) => pixelAt(f, x0, y)).filter(Boolean);
    expect(lit.length).toBeGreaterThan(0);
  });

  test("the build sweep turns source to ink behind a glint band", () => {
    const t = (state.buildAt + loadingMs) / 2;
    const seen = tones(at(t));
    expect(seen.has("ink")).toBe(true);
    expect(seen.has("glint")).toBe(true);
    expect(seen.has("accent")).toBe(true);
  });

  test("LOADING ends on the settled word", () => {
    const end = at(loadingMs);
    for (const c of litCells(layout)) expect(pixelAt(end, c.x, c.y)).toEqual({ tone: "ink", alpha: 1 });
    expect(count(end)).toBe(litCells(layout).length);
  });

  test("LIVE edits glyphs and reruns the build, and always returns to the word", () => {
    const events = Array.from({ length: 60 }, (_, i) => liveEvent(state, i));
    expect(events.some((e) => e.kind === "edit")).toBe(true);
    expect(events.some((e) => e.kind === "rebuild")).toBe(true);
    expect(new Set(events.map((e) => e.slot)).size).toBeGreaterThan(3);
    const seen = new Set<string>();
    let settledFrames = 0;
    for (let t = loadingMs; t < loadingMs + 60_000; t += 40) {
      const f = at(t);
      for (const tone of tones(f)) seen.add(tone);
      if ([...tones(f)].join() === "ink" && count(f) === litCells(layout).length) settledFrames += 1;
    }
    expect([...seen].sort()).toEqual(["accent", "glint", "ink"]);
    expect(settledFrames).toBeGreaterThan(0);
  });

  test("frames are pure in time", () => {
    for (const t of [90, 777, 1500, loadingMs + 4321]) expect(at(t)).toEqual(at(t));
  });

  test("LIVE off settles on the plain word", () => {
    expect([...tones(at(loadingMs + 5000, false))]).toEqual(["ink"]);
  });
});
