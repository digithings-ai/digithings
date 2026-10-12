import { describe, expect, test } from "bun:test";

import { DIGICLAW } from "../src/definitions";
import { preparedBanner, sampleBanner, terminalFit } from "../src/engine";
import { litCells, pixelAt } from "../src/layout";
import { HEADROOM, liveEvent, type ClawState } from "../src/animations/claw";
import type { Frame } from "../src/types";

const { layout } = preparedBanner(DIGICLAW);
const state = preparedBanner(DIGICLAW).state as ClawState;
const loadingMs = DIGICLAW.animation.loadingMs(state);
const tones = (f: Frame) => new Set(f.pixels.filter(Boolean).map((p) => p!.tone));
const at = (t: number, live = true) => sampleBanner(DIGICLAW, { t, live }).frame;
const count = (f: Frame) => f.pixels.filter(Boolean).length;
const headroomLit = (f: Frame) => f.pixels.slice(0, HEADROOM * f.width).filter(Boolean).length;

describe("digiclaw CLAW", () => {
  test("the font carries blank headroom over every glyph", () => {
    expect(layout.height).toBe(DIGICLAW.font.rows);
    expect(layout.height % 2).toBe(0);
    for (const c of litCells(layout)) expect(c.y).toBeGreaterThanOrEqual(HEADROOM);
  });

  test("LOADING opens on a sunk, dim pile under a rail", () => {
    const f = at(0);
    expect([...tones(f)]).toEqual(["accent"]);
    for (const p of f.pixels.filter(Boolean)) expect(p!.alpha).toBeLessThan(0.5);
    for (const s of state.sinks) expect(s).toBeGreaterThanOrEqual(5);
    // The rail is the only thing in the headroom; no glyph sits at home yet.
    expect(headroomLit(f)).toBe(layout.width);
  });

  test("glyphs are placed left to right, and one grab slips and is retried", () => {
    const placed = state.script.placed as number[];
    for (let i = 1; i < placed.length; i += 1) expect(placed[i]).toBeGreaterThan(placed[i - 1]);
    expect(state.slipSlot).toBeGreaterThan(1);
    const drop = state.script.dropped;
    expect(drop.length).toBe(1);
    expect(drop[0].slot).toBe(state.slipSlot);
    expect(drop[0].t).toBeLessThan(placed[state.slipSlot]);
  });

  test("the claw speeds up: later grabs take less time than early ones", () => {
    const placed = state.script.placed as number[];
    const gaps = placed.slice(1).map((p, i) => p - placed[i]);
    expect(gaps.at(-1)!).toBeLessThan(gaps[0]);
  });

  test("a released glyph flashes glint, then settles to ink", () => {
    const t0 = state.script.placed[0]!;
    const cells = litCells(layout).filter((c) => c.glyph === 0);
    for (const c of cells.slice(-5)) expect(pixelAt(at(t0 + 1), c.x, c.y)?.tone).toBe("glint");
    for (const c of cells) expect(pixelAt(at(t0 + state.options.flashMs + 1), c.x, c.y)).toEqual({ tone: "ink", alpha: 1 });
  });

  test("LOADING ends on the settled word and stays under five seconds", () => {
    expect(loadingMs).toBeLessThan(5000);
    const end = at(loadingMs);
    for (const c of litCells(layout)) expect(pixelAt(end, c.x, c.y)).toEqual({ tone: "ink", alpha: 1 });
    expect(count(end)).toBe(litCells(layout).length);
  });

  test("LIVE plucks and slips glyphs, and always returns to the word", () => {
    const events = Array.from({ length: 60 }, (_, i) => liveEvent(state, i));
    expect(events.some((e) => e.kind === "pluck")).toBe(true);
    expect(events.some((e) => e.kind === "slip")).toBe(true);
    expect(new Set(events.map((e) => e.slot)).size).toBeGreaterThan(4);
    const seen = new Set<string>();
    let settledFrames = 0;
    let lifted = 0;
    for (let t = loadingMs; t < loadingMs + 60_000; t += 40) {
      const f = at(t);
      for (const tone of tones(f)) seen.add(tone);
      if ([...tones(f)].join() === "ink" && count(f) === litCells(layout).length) settledFrames += 1;
      if (f.pixels.slice(0, HEADROOM * f.width).some((p) => p?.tone === "ink")) lifted += 1;
    }
    expect([...seen].sort()).toEqual(["accent", "glint", "ink"]);
    expect(settledFrames).toBeGreaterThan(0);
    expect(lifted).toBeGreaterThan(0);
  });

  test("frames are pure in time", () => {
    for (const t of [90, 777, 1500, loadingMs + 4321]) expect(at(t)).toEqual(at(t));
  });

  test("LIVE off and reduced motion settle on the plain word", () => {
    expect([...tones(at(loadingMs + 5000, false))]).toEqual(["ink"]);
    const still = sampleBanner(DIGICLAW, { t: 0, motion: "reduced" }).frame;
    expect(count(still)).toBe(litCells(layout).length);
  });

  test("fits 120x30 and 80x24 terminals", () => {
    expect(terminalFit(DIGICLAW, { cols: 120, rows: 30 })).not.toBeNull();
    expect(terminalFit(DIGICLAW, { cols: 80, rows: 24 })).not.toBeNull();
  });
});
