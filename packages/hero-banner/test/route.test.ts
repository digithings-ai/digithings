import { describe, expect, test } from "bun:test";

import { DIGILLM } from "../src/definitions";
import { preparedBanner, sampleBanner } from "../src/engine";
import { litCells, pixelAt } from "../src/layout";
import type { RouteState } from "../src/animations/route";
import type { Frame } from "../src/types";

const { layout } = preparedBanner(DIGILLM);
const state = preparedBanner(DIGILLM).state as RouteState;
const loadingMs = DIGILLM.animation.loadingMs(state);
const tones = (f: Frame) => new Set(f.pixels.filter(Boolean).map((p) => p!.tone));
const at = (t: number, live = true) => sampleBanner(DIGILLM, { t, live }).frame;

describe("digillm ROUTE", () => {
  test("the request fans out: centre lanes lead the outer lanes", () => {
    const f = at(300);
    const reach = (y: number) => Math.max(-1, ...Array.from({ length: f.width }, (_, x) => (pixelAt(f, x, y) ? x : -1)));
    expect(reach(4)).toBeGreaterThan(reach(0));
    expect(reach(5)).toBeGreaterThan(reach(9));
  });

  test("cells the request crossed are pending until the reply confirms them", () => {
    const f = at(state.returnStartMs - 1);
    const alphas = new Set(litCells(layout).map((c) => pixelAt(f, c.x, c.y)?.alpha));
    expect(alphas.has(0.45)).toBe(true);
    const end = at(loadingMs - 1);
    for (const c of litCells(layout)) expect(pixelAt(end, c.x, c.y)).toEqual({ tone: "ink", alpha: 1 });
  });

  test("the reply runs back from the right", () => {
    const f = at(state.returnStartMs + 150);
    const accents = f.pixels.flatMap((p, i) => (p?.tone === "accent" && p.alpha === 1 ? [i % f.width] : []));
    expect(accents.length).toBeGreaterThan(0);
    expect(Math.min(...accents)).toBeGreaterThan(f.width / 2);
  });

  test("LIVE sends packets, some of them replies, and keeps the word", () => {
    const seen = new Set<string>();
    for (let t = loadingMs; t < loadingMs + 30_000; t += 50) {
      const f = at(t);
      for (const tone of tones(f)) seen.add(tone);
      for (const c of litCells(layout)) expect(pixelAt(f, c.x, c.y)).not.toBeNull();
    }
    expect([...seen].sort()).toEqual(["accent", "ink", "reply"]);
  });

  test("frames are pure in time", () => {
    for (const t of [90, 777, 1500, loadingMs + 4321]) expect(at(t)).toEqual(at(t));
  });

  test("LIVE off settles on the plain word", () => {
    const f = at(loadingMs + 5000, false);
    expect([...tones(f)]).toEqual(["ink"]);
  });
});
