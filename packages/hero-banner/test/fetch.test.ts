import { describe, expect, test } from "bun:test";

import { DIGIFETCH } from "../src/definitions";
import { preparedBanner, sampleBanner } from "../src/engine";
import { litCells, pixelAt } from "../src/layout";
import { liveFetch, type FetchState } from "../src/animations/fetch";
import type { Frame } from "../src/types";

const { layout } = preparedBanner(DIGIFETCH);
const state = preparedBanner(DIGIFETCH).state as FetchState;
const loadingMs = DIGIFETCH.animation.loadingMs(state);
const tones = (f: Frame) => new Set(f.pixels.filter(Boolean).map((p) => p!.tone));
const at = (t: number, live = true) => sampleBanner(DIGIFETCH, { t, live }).frame;
const count = (f: Frame) => f.pixels.filter(Boolean).length;

describe("digifetch FETCH", () => {
  test("LOADING opens with the request alone on the middle row", () => {
    const f = at(state.requestMs / 2);
    const rows = new Set(f.pixels.flatMap((p, i) => (p ? [Math.floor(i / layout.width)] : [])));
    expect([...rows]).toEqual([layout.height >> 1]);
    expect(tones(f).has("glint")).toBe(true);
  });

  test("one packet per lit cell, launched after the request, left columns first", () => {
    expect(state.packets.length).toBe(litCells(layout).length);
    for (const p of state.packets) expect(p.launch).toBeGreaterThanOrEqual(state.requestMs);
    const byX = [...state.packets].sort((a, b) => a.x - b.x);
    expect(byX[0].launch).toBeLessThan(byX.at(-1)!.launch);
  });

  test("packets arrive from the right: nothing is drawn left of a packet's home before it lands", () => {
    for (const t of [loadingMs * 0.3, loadingMs * 0.5, loadingMs * 0.7]) {
      const f = at(t);
      const rows = new Map<number, number>();
      for (const p of state.packets) if (t < p.land) rows.set(p.y, Math.min(rows.get(p.y) ?? Infinity, p.x));
      for (const [y, home] of rows) {
        // Left of the leftmost unlanded home on a row, only landed ink/glint cells may show.
        for (let x = 0; x < home; x += 1) {
          const px = pixelAt(f, x, y);
          if (px) expect(state.lit[y * layout.width + x]).toBe(1);
        }
      }
    }
  });

  test("mid-load shows packets (glint), trails (accent) and landed word (ink)", () => {
    const lands = state.packets.map((p) => p.land).sort((a, b) => a - b);
    const t = lands[Math.floor(lands.length / 2)] + DIGIFETCH.animation.liveTickMs * 5;
    expect([...tones(at(t))].sort()).toEqual(["accent", "glint", "ink"]);
  });

  test("LOADING ends on the settled word", () => {
    const end = at(loadingMs);
    for (const c of litCells(layout)) expect(pixelAt(end, c.x, c.y)).toEqual({ tone: "ink", alpha: 1 });
    expect(count(end)).toBe(litCells(layout).length);
  });

  test("LIVE responses land on the word near the request row", () => {
    for (let i = 0; i < 50; i += 1) {
      const f = liveFetch(state, i);
      expect(f.packets.length).toBeGreaterThanOrEqual(1);
      for (const p of f.packets) {
        expect(state.lit[p.y * layout.width + p.x]).toBe(1);
        expect(Math.abs(p.y - f.y)).toBeLessThanOrEqual(1);
        expect(p.launch).toBeGreaterThan(f.at);
      }
    }
  });

  test("LIVE keeps the word and uses accent and glint", () => {
    const seen = new Set<string>();
    for (let t = loadingMs; t < loadingMs + 30_000; t += 40) {
      const f = at(t);
      for (const tone of tones(f)) seen.add(tone);
      for (const c of litCells(layout)) expect(pixelAt(f, c.x, c.y)).not.toBeNull();
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
