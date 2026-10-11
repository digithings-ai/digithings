import { describe, expect, test } from "bun:test";

import { paintFrame } from "../src/canvas";
import { BANNERS, DIGICHAT, DIGITHINGS, DIGIVOICE_BASELINE as DIGIVOICE } from "../src/definitions";
import {
  assertDefinition,
  claimLoading,
  memoryStore,
  nextTickMs,
  preparedBanner,
  resolveLive,
  resolveMotion,
  sampleBanner,
} from "../src/engine";
import { PIXEL_7X10 } from "../src/font";
import { bannerLines, nearestCube, toAnsi, toPlain } from "../src/tui";
import type { BannerDefinition, Frame } from "../src/types";
// @ts-expect-error untyped legacy JS
import { wordmarkText as legacyVoiceText } from "./legacy/digivoice-hero.js";

const lit = (f: Frame) => f.pixels.filter(Boolean).length;
const all = Object.values(BANNERS);

describe("definition rules", () => {
  test("every banner is ALL CAPS with a lowercase label", () => {
    for (const def of all) {
      expect(def.text).toBe(def.text.toUpperCase());
      expect(def.label).toBe(def.id);
      expect(() => assertDefinition(def)).not.toThrow();
    }
  });

  test("lowercase banner text is refused", () => {
    const bad: BannerDefinition = { ...DIGICHAT, text: "digichat" };
    expect(() => assertDefinition(bad)).toThrow(/ALL CAPS/);
  });

  test("a missing glyph is refused", () => {
    const bad: BannerDefinition = { ...DIGICHAT, text: "DIGI~" };
    expect(() => assertDefinition(bad)).toThrow(/no glyph/);
  });

  test("the family font is 7x10, two pixels per terminal row", () => {
    expect([PIXEL_7X10.cols, PIXEL_7X10.rows]).toEqual([7, 10]);
    for (const glyph of Object.values(PIXEL_7X10.glyphs)) {
      expect(glyph.length).toBe(10);
      for (const row of glyph) expect(row.length).toBe(7);
    }
  });
});

describe("LOADING, LIVE, still", () => {
  for (const def of all) {
    test(`${def.id}: loading, then live, then still when live is off`, () => {
      const { state } = preparedBanner(def);
      const loadingMs = def.animation.loadingMs(state);
      expect(loadingMs).toBeGreaterThan(0);
      expect(sampleBanner(def, { t: 0 }).phase).toBe("loading");
      expect(sampleBanner(def, { t: loadingMs + 1 }).phase).toBe("live");
      const off = sampleBanner(def, { t: loadingMs + 1, live: false });
      expect(off.phase).toBe("still");
      expect(off.frame).toEqual(def.animation.still(state));
      expect(nextTickMs(def, "still")).toBeNull();
    });

    test(`${def.id}: reduced motion is the settled mark at every moment`, () => {
      const still = def.animation.still(preparedBanner(def).state);
      for (const t of [0, 100, 1000, 5000, 60_000]) {
        const s = sampleBanner(def, { t, motion: "reduced" });
        expect(s.phase).toBe("still");
        expect(s.frame).toEqual(still);
      }
      expect(lit(still)).toBeGreaterThan(100);
    });

    test(`${def.id}: skipping LOADING starts in LIVE at t=0`, () => {
      expect(sampleBanner(def, { t: 0, skipLoading: true }).phase).toBe("live");
    });
  }

  test("digithings LOADING starts empty and builds in", () => {
    expect(lit(sampleBanner(DIGITHINGS, { t: 0 }).frame)).toBe(0);
    expect(lit(sampleBanner(DIGITHINGS, { t: 400 }).frame)).toBeGreaterThan(0);
  });

  test("digivoice still is hero.js's default frame (tMs = BUILD_MS)", () => {
    const ours = bannerLines(DIGIVOICE, { cols: 120, t: 0, motion: "reduced", mode: "256", scale: 1 });
    const legacy: string[] = legacyVoiceText("DIGIVOICE", { cols: 120, tMs: 1400, scale: 1 });
    expect(toPlain(ours.lines).map((l) => l.replaceAll("█", "▀"))).toEqual(legacy);
  });
});

describe("motion and live config", () => {
  test("prefers-reduced-motion and NO_MOTION both reduce", () => {
    expect(resolveMotion({ prefersReduced: true })).toBe("reduced");
    expect(resolveMotion({ env: { NO_MOTION: "1" } })).toBe("reduced");
    expect(resolveMotion({ env: { NO_MOTION: "0" } })).toBe("full");
    expect(resolveMotion({ env: { HERO_BANNER_MOTION: "reduce" } })).toBe("reduced");
    expect(resolveMotion({ env: {} })).toBe("full");
  });

  test("live: surface config, then HERO_BANNER_LIVE, then the definition", () => {
    expect(resolveLive(DIGITHINGS, {})).toBe(true);
    expect(resolveLive(DIGITHINGS, { env: { HERO_BANNER_LIVE: "off" } })).toBe(false);
    expect(resolveLive(DIGITHINGS, { env: { HERO_BANNER_LIVE: "off" }, config: true })).toBe(true);
  });

  test("LOADING plays once per store", () => {
    const store = memoryStore();
    expect(claimLoading(DIGICHAT, store)).toBe(true);
    expect(claimLoading(DIGICHAT, store)).toBe(false);
    expect(claimLoading(DIGIVOICE, store)).toBe(true);
    expect(claimLoading(DIGICHAT, null)).toBe(true);
  });
});

describe("terminal fit", () => {
  for (const def of all) {
    test(`${def.id} fits 120x30 and 80x24 as five half-block rows`, () => {
      for (const [cols, rows] of [[120, 30], [80, 24]] as const) {
        const out = bannerLines(def, { cols, rows, t: 0, motion: "reduced", mode: "truecolor" });
        expect(out.compact).toBe(false);
        expect(out.lines.length).toBe(5);
        expect(out.width).toBeLessThanOrEqual(cols - 2);
        for (const line of toPlain(out.lines)) expect(line.length).toBe(out.width);
      }
    });
  }

  test("DIGITHINGS drops to gap 0 at 80 columns, keeps gap 2 at 120", () => {
    expect(bannerLines(DIGITHINGS, { cols: 120, rows: 30, t: 0, mode: "256" }).gap).toBe(2);
    expect(bannerLines(DIGITHINGS, { cols: 80, rows: 24, t: 0, mode: "256" }).gap).toBe(0);
  });

  test("a wide, tall terminal scales the mark up", () => {
    const out = bannerLines(DIGICHAT, { cols: 240, rows: 60, t: 0, motion: "reduced", mode: "256" });
    expect(out.scale).toBe(3);
    expect(out.lines.length).toBe(15);
  });

  test("too narrow falls back to the text on one line", () => {
    const out = bannerLines(DIGITHINGS, { cols: 40, rows: 24, t: 0, mode: "256" });
    expect(out.compact).toBe(true);
    expect(toPlain(out.lines)).toEqual(["DIGITHINGS"]);
  });

  test("one SGR colour mode per cell", () => {
    for (const mode of ["truecolor", "256"] as const) {
      const ansi = toAnsi(bannerLines(DIGITHINGS, { cols: 120, t: 600, mode }).lines).join("\n");
      expect(ansi.includes(mode === "truecolor" ? ";5;" : ";2;")).toBe(false);
    }
  });

  test("cube lookup", () => {
    expect(nearestCube([255, 255, 255])).toBe(231);
    expect(nearestCube([95, 95, 95])).toBe(59);
    expect(nearestCube([8, 8, 8])).toBe(232);
  });
});

describe("canvas renderer", () => {
  test("paints one square per lit pixel at its alpha", () => {
    const calls: [string, number, number[]][] = [];
    const ctx = {
      fillStyle: "" as string,
      globalAlpha: 1,
      clearRect() {},
      fillRect(...args: number[]) {
        calls.push([String(this.fillStyle), this.globalAlpha, args]);
      },
    };
    const frame = sampleBanner(DIGITHINGS, { t: 0, motion: "reduced" }).frame;
    paintFrame(ctx, frame, { pixel: 4, colors: { ink: "#eceef0", accent: "#fff", ground: "#000" } });
    expect(calls.length).toBe(lit(frame));
    expect(calls[0]![2]![2]).toBe(4);
    expect(new Set(calls.map((c) => c[1]))).toEqual(new Set([0.36, 0.5, 0.66, 0.82, 1]));
  });
});

describe("digiquant shows red and green days (DIG-2866)", () => {
  const tones = (t: number, extra: Partial<Parameters<typeof sampleBanner>[1]> = {}) => {
    const out = new Set<string>();
    for (const p of sampleBanner(BANNERS.digiquant, { t, ...extra }).frame.pixels) if (p) out.add(p.tone);
    return out;
  };
  const span = (from: number, to: number, extra = {}) => {
    const out = new Set<string>();
    for (let t = from; t < to; t += 40) for (const tone of tones(t, extra)) out.add(tone);
    return out;
  };

  test("LOADING builds in both up and down, never the accent", () => {
    const seen = span(0, 1900);
    expect(seen.has("up") && seen.has("down")).toBe(true);
    expect(seen.has("accent")).toBe(false);
  });

  test("LIVE keeps flashing both up and down, never the accent", () => {
    const seen = span(4000, 20000);
    expect(seen.has("up") && seen.has("down")).toBe(true);
    expect(seen.has("accent")).toBe(false);
  });

  test("a reload that skips LOADING still flashes both up and down", () => {
    const seen = span(4000, 20000, { skipLoading: true });
    expect(seen.has("up") && seen.has("down")).toBe(true);
  });

  test("reduced motion is the settled ink mark", () => {
    expect([...tones(5000, { motion: "reduced" })]).toEqual(["ink"]);
  });
});
