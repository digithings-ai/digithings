import { describe, expect, test } from "bun:test";

import { DIGIVAULT } from "../src/definitions";
import { preparedBanner, sampleBanner } from "../src/engine";
import { litCells, pixelAt } from "../src/layout";
import { dialAt, liveEvent, type VaultState } from "../src/animations/vault";
import type { Frame } from "../src/types";

const { layout } = preparedBanner(DIGIVAULT);
const state = preparedBanner(DIGIVAULT).state as VaultState;
const loadingMs = DIGIVAULT.animation.loadingMs(state);
const tones = (f: Frame) => new Set(f.pixels.filter(Boolean).map((p) => p!.tone));
const at = (t: number, live = true) => sampleBanner(DIGIVAULT, { t, live }).frame;
const count = (f: Frame) => f.pixels.filter(Boolean).length;

describe("digivault VAULT", () => {
  test("LOADING opens on a closed door: plate over the word, dark seam, bolts across it", () => {
    const f = at(0);
    expect([...tones(f)]).toEqual(["accent"]);
    for (let y = 0; y < layout.height; y += 1) expect(pixelAt(f, state.seam, y)).toBeNull();
    // Dark off the seam only where the dial's hand is cut, inside the dial.
    const { cx, cy, r } = state.dial;
    let cut = 0;
    for (let y = 0; y < layout.height; y += 1) {
      for (let x = 0; x < layout.width; x += 1) {
        if (x === state.seam || pixelAt(f, x, y)) continue;
        cut += 1;
        expect(Math.hypot(x - cx, y - cy)).toBeLessThan(r + 0.6);
      }
    }
    expect(cut).toBeGreaterThan(1);
    expect(count(f)).toBe(layout.width * layout.height - layout.height - cut);
    for (const y of state.boltRows) {
      expect(pixelAt(f, state.seam - 1, y)?.alpha).toBe(0.9);
      expect(pixelAt(f, state.seam + 1, y)?.alpha).toBe(0.9);
    }
  });

  test("the turning hand changes the door's shape, not only its colour", () => {
    const { turnMs } = state.options;
    const lit = (f: Frame) => f.pixels.map((p) => (p ? 1 : 0)).join("");
    expect(lit(at(turnMs * 0.1))).not.toBe(lit(at(turnMs * 1.5)));
  });

  test("the dial turns right, left, right and clicks at each stop", () => {
    const { turnMs } = state.options;
    const stops = [0, 1, 2].map((i) => dialAt(state, (i + 1) * turnMs - 1));
    expect(stops.every((s) => s.click)).toBe(true);
    expect(stops[0].turn).toBeGreaterThan(0);
    expect(stops[1].turn).toBeLessThan(stops[0].turn);
    expect(stops[2].turn).toBeGreaterThan(stops[1].turn);
    expect(dialAt(state, turnMs / 3).click).toBe(false);
    expect(tones(at(turnMs - 1)).has("glint")).toBe(true);
  });

  test("the bolts slide back off the seam before the door opens", () => {
    const f = at(state.openAt - 1);
    for (const y of state.boltRows) {
      expect(pixelAt(f, state.seam - 1, y)?.alpha).toBe(0.22);
      expect(pixelAt(f, state.seam + state.boltLen + 1, y)?.alpha).toBe(0.9);
    }
  });

  test("the leaves part and show the word in accent behind glint edges", () => {
    const f = at(state.openAt + state.options.openMs / 2);
    expect(tones(f).has("glint")).toBe(true);
    const centre = litCells(layout).filter((c) => Math.abs(c.x - state.seam) < 3);
    expect(centre.length).toBeGreaterThan(0);
    for (const c of centre) expect(pixelAt(f, c.x, c.y)).toEqual({ tone: "accent", alpha: 0.9 });
  });

  test("LOADING ends on the settled word", () => {
    const end = at(loadingMs);
    for (const c of litCells(layout)) expect(pixelAt(end, c.x, c.y)).toEqual({ tone: "ink", alpha: 1 });
    expect(count(end)).toBe(litCells(layout).length);
  });

  test("LIVE scans and relocks, and always returns to the word", () => {
    const events = Array.from({ length: 60 }, (_, i) => liveEvent(state, i));
    expect(events.some((e) => e.kind === "scan")).toBe(true);
    expect(events.some((e) => e.kind === "relock")).toBe(true);
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
    for (const t of [90, 777, 2000, loadingMs + 4321]) expect(at(t)).toEqual(at(t));
  });

  test("LIVE off settles on the plain word", () => {
    expect([...tones(at(loadingMs + 5000, false))]).toEqual(["ink"]);
  });
});
