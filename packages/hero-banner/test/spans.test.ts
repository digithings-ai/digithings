import { describe, expect, test } from "bun:test";

import { DIGITRACE } from "../src/definitions";
import { preparedBanner, sampleBanner } from "../src/engine";
import { litCells, pixelAt } from "../src/layout";
import { liveTrace, type SpansState } from "../src/animations/spans";
import type { Frame } from "../src/types";

const { layout } = preparedBanner(DIGITRACE);
const state = preparedBanner(DIGITRACE).state as SpansState;
const loadingMs = DIGITRACE.animation.loadingMs(state);
const tones = (f: Frame) => new Set(f.pixels.filter(Boolean).map((p) => p!.tone));
const at = (t: number, live = true) => sampleBanner(DIGITRACE, { t, live }).frame;
const count = (f: Frame) => f.pixels.filter(Boolean).length;

describe("digitrace SPANS", () => {
  test("LOADING starts empty", () => {
    expect(count(at(0))).toBe(0);
  });

  test("every lane is tiled by sibling spans, no gaps or overlaps", () => {
    for (let lane = 0; lane < layout.height; lane += 1) {
      const spans = state.spans.filter((s) => s.lane === lane).sort((p, q) => p.a - q.a);
      expect(spans.length).toBeGreaterThanOrEqual(1);
      expect(spans[0].a).toBe(0);
      expect(spans.at(-1)!.b).toBe(layout.width);
      for (let i = 1; i < spans.length; i += 1) expect(spans[i].a).toBe(spans[i - 1].b);
    }
  });

  test("waterfall: lower lanes open later", () => {
    const firstOpen = (lane: number) => Math.min(...state.spans.filter((s) => s.lane === lane).map((s) => s.open));
    for (let lane = 1; lane < layout.height; lane += 1) expect(firstOpen(lane)).toBeGreaterThan(firstOpen(lane - 1));
  });

  test("mid-load shows bars (accent), heads (glint) and the word (ink)", () => {
    const seen = tones(at(loadingMs * 0.4));
    expect([...seen].sort()).toEqual(["accent", "glint", "ink"]);
  });

  test("the word is never drawn ahead of its span", () => {
    const t = loadingMs * 0.3;
    const f = at(t);
    for (const s of state.spans) {
      if (t >= s.open) continue;
      for (let x = s.a; x < s.b; x += 1) expect(pixelAt(f, x, s.lane)).toBeNull();
    }
  });

  test("LOADING ends on the settled word", () => {
    const end = at(loadingMs);
    for (const c of litCells(layout)) expect(pixelAt(end, c.x, c.y)).toEqual({ tone: "ink", alpha: 1 });
    expect(count(end)).toBe(litCells(layout).length);
  });

  test("LIVE traces nest: children below the root, inside its columns, opening after it", () => {
    for (let i = 0; i < 50; i += 1) {
      const [root, ...kids] = liveTrace(state, i);
      expect(kids.length).toBeGreaterThanOrEqual(1);
      kids.forEach((k, j) => {
        expect(k.lane).toBe(root.lane + j + 1);
        expect(k.lane).toBeLessThan(layout.height);
        expect(k.a).toBeGreaterThanOrEqual(root.a);
        expect(k.b).toBeLessThanOrEqual(root.b);
        expect(k.open).toBeGreaterThan(root.open);
      });
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
