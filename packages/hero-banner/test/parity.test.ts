/**
 * No visual regression: each ported definition draws what its legacy mark drew.
 * The legacy generators are verbatim copies in test/legacy (digithings and
 * digiquant cell parameters, digivoice frames); digichat is compared against
 * the live module on develop.
 */
import { describe, expect, test } from "bun:test";

import { heroWordmarkLines } from "../../ui/src/components/chat/digichat-wordmark";
import type { BuildState } from "../src/animations/build";
import type { RiseState } from "../src/animations/rise";
import { scrambleAnimation } from "../src/animations/scramble";
import { DIGICHAT, DIGICHAT_SCRAMBLE, DIGIQUANT, DIGITHINGS, DIGIVOICE_BASELINE as DIGIVOICE } from "../src/definitions";
import { preparedBanner } from "../src/engine";
import { bannerLines, type TermCell, type TermColor } from "../src/tui";
import { LEGACY_DIGIQUANT } from "./legacy/digiquant-cells";
import { LEGACY_DIGITHINGS } from "./legacy/digithings-cells";
// @ts-expect-error untyped legacy JS
import { wordmarkLines as legacyVoiceLines } from "./legacy/digivoice-hero.js";

const ms = (v: unknown) => Number(String(v).replace("ms", ""));

describe("digithings BUILD matches PixelWordmark.tsx", () => {
  const state = preparedBanner(DIGITHINGS).state as BuildState;

  test("same letter cells, timings, opacity steps and glints", () => {
    expect(state.cells.length).toBe(LEGACY_DIGITHINGS.letters.length);
    LEGACY_DIGITHINGS.letters.forEach((legacy, i) => {
      const cell = state.cells[i]!;
      const s = legacy.style as Record<string, string | number>;
      expect([cell.x, cell.y]).toEqual([legacy.x, legacy.y]);
      expect([cell.d, cell.t]).toEqual([ms(s["--d"]), ms(s["--t"])]);
      expect([cell.a, cell.b, cell.c, cell.f]).toEqual([s["--a"], s["--b"], s["--c"], s["--f"]] as number[]);
      expect(cell.glint != null).toBe(legacy.glint);
      if (cell.glint) expect([cell.glint.g, cell.glint.gp]).toEqual([ms(s["--g"]), ms(s["--gp"])]);
    });
  });

  test("same strays", () => {
    expect(state.strays.map((c) => [c.x, c.y, c.d, c.t])).toEqual(
      LEGACY_DIGITHINGS.stray.map((c) => {
        const s = c.style as Record<string, string>;
        return [c.x, c.y, ms(s["--d"]), ms(s["--t"])];
      }),
    );
  });
});

describe("digiquant RISE matches QuantWordmark.tsx (#4986)", () => {
  const state = preparedBanner(DIGIQUANT).state as RiseState;
  const tone = (s: Record<string, unknown>) => (String(s["--dq-cell"]).includes("--up") ? "up" : "down");

  test("same cells, column sweep, rise, tone and glint", () => {
    expect(state.cells.length).toBe(LEGACY_DIGIQUANT.letters.length);
    LEGACY_DIGIQUANT.letters.forEach((legacy, i) => {
      const cell = state.cells[i]!;
      const s = legacy.style as Record<string, string>;
      const rise = /dq-rise (\d+)ms \S+ (\d+)ms/.exec(String(s.animation))!;
      expect([cell.x, cell.y, cell.dur, cell.delay]).toEqual([legacy.x, legacy.y, Number(rise[1]), Number(rise[2])]);
      expect(cell.tone).toBe(tone(s));
      const glint = /dq-glint (\d+)ms step-end (\d+)ms/.exec(String(s.animation));
      expect(cell.glint ? [cell.glint.period, cell.glint.offset] : null).toEqual(
        glint ? [Number(glint[1]), Number(glint[2])] : null,
      );
    });
  });

  test("same strays and blinks", () => {
    expect(state.strays.map((c) => [c.x, c.y, c.dur, c.delay, c.tone, c.blink && [c.blink.period, c.blink.offset]])).toEqual(
      LEGACY_DIGIQUANT.strays.map((c) => {
        const s = c.style as Record<string, string>;
        const m = /dq-stray (\d+)ms linear (\d+)ms/.exec(String(s.animation))!;
        const b = /dq-blink (\d+)ms step-end (\d+)ms/.exec(String(s.animation));
        return [c.x, c.y, Number(m[1]), Number(m[2]), tone(s), b && [Number(b[1]), Number(b[2])]];
      }),
    );
  });

  test("glints and blinks each show both up and down", () => {
    const glints = new Set(state.cells.filter((c) => c.glint).map((c) => c.tone));
    const blinks = new Set(state.strays.filter((c) => c.blink).map((c) => c.tone));
    expect([...glints].sort()).toEqual(["down", "up"]);
    expect([...blinks].sort()).toEqual(["down", "up"]);
  });
});

type LegacyCell = { ch: string; color: { rgb: number | number[] } | { cube: number } | null; bg?: unknown };

function legacyHex(color: LegacyCell["color"]): TermColor | null {
  if (!color) return null;
  if ("cube" in color) return { cube: color.cube };
  const n = color.rgb as number;
  const h = n.toString(16).padStart(2, "0");
  return { hex: `#${h}${h}${h}` };
}

/** What a cell looks like: top and bottom pixel colours. ▀ with equal fg/bg is █. */
function looks(cell: { ch: string; fg: TermColor | null; bg: TermColor | null }): string {
  const key = (c: TermColor | null) => (c ? JSON.stringify(c) : "-");
  if (cell.ch === " ") return "  ";
  if (cell.ch === "█") return `${key(cell.fg)}|${key(cell.fg)}`;
  if (cell.ch === "▀") return `${key(cell.fg)}|${cell.bg ? key(cell.bg) : "-"}`;
  return `-|${key(cell.fg)}`;
}

describe("digichat SCRAMBLE matches digichat-wordmark.ts", () => {
  // The legacy idle (LIVE `flash`). DIGICHAT itself streams in LIVE (DIG-2865);
  // its LOADING is the same recipe, so it must match up to the end of LOADING.
  const legacyIdle = { ...DIGICHAT, animation: scrambleAnimation(DIGICHAT_SCRAMBLE) };
  const loadingMs = DIGICHAT.animation.loadingMs(preparedBanner(DIGICHAT).state);
  for (const truecolor of [true, false]) {
    test(`every 40ms frame for 20s, ${truecolor ? "truecolor" : "256"}`, () => {
      for (const cols of [120, 80, 70]) {
        for (let t = 0; t <= 20_000; t += 40) {
          const legacy = heroWordmarkLines("DIGICHAT", { cols, elapsed: t, full: true, truecolor });
          const mode = truecolor ? "truecolor" : "256";
          const ours = bannerLines(legacyIdle, { cols, t, mode, scale: 1 });
          const a = legacy.lines.map((row) => row.map((c) => looks({ ch: c.ch, fg: legacyHex(c.color), bg: null })));
          const b = ours.lines.map((row: TermCell[]) => row.map(looks));
          expect(b).toEqual(a);
          if (t < loadingMs) {
            const streamed = bannerLines(DIGICHAT, { cols, t, mode, scale: 1 });
            expect(streamed.lines.map((row: TermCell[]) => row.map(looks))).toEqual(a);
          }
        }
      }
    });
  }
});

describe("digivoice EQUALIZER matches hero.js", () => {
  for (const truecolor of [true, false]) {
    test(`every 60ms frame from 1.4s to 8s, ${truecolor ? "truecolor" : "256"}`, () => {
      for (let t = 1400; t <= 8000; t += 60) {
        const legacy = legacyVoiceLines("DIGIVOICE", { cols: 120, tMs: t, truecolor, scale: 1 });
        const ours = bannerLines(DIGIVOICE, { cols: 120, t, mode: truecolor ? "truecolor" : "256", scale: 1 });
        const a = (legacy.lines as LegacyCell[][]).map((row) =>
          row.map((c) => looks({ ch: c.ch, fg: legacyHex(c.color), bg: legacyHex((c.bg as LegacyCell["color"]) ?? null) })),
        );
        const b = ours.lines.map((row: TermCell[]) => row.map(looks));
        expect(b).toEqual(a);
      }
    });
  }
});
