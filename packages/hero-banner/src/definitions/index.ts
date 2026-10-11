import { buildAnimation } from "../animations/build";
import { equalizerAnimation } from "../animations/equalizer";
import { riseAnimation } from "../animations/rise";
import { scrambleAnimation, type ScrambleOptions } from "../animations/scramble";
import { PIXEL_7X10 } from "../font";
import type { BannerDefinition, Tone } from "../types";

/**
 * The four ported banners. Each one is the single source for its TUI and web
 * marks. Timings and seeds are the legacy marks' own, so the port draws the
 * same cells (see test/parity.test.ts).
 */

const INK: Tone = { hex: "#ECEEF0", cube: 255, cssVar: "--ink" };
const GROUND: Tone = { hex: "#0A0E0C", cube: 232, cssVar: "--bg" };

/** apps/digithings-web/components/landing/PixelWordmark.tsx */
export const DIGITHINGS: BannerDefinition = {
  id: "digithings",
  text: "DIGITHINGS",
  label: "digithings",
  font: PIXEL_7X10,
  gap: 2,
  palette: { ink: INK, ground: GROUND, accent: { hex: "#FFFFFF", cube: 231, cssVar: "--glint" } },
  animation: buildAnimation({ steps: [0.36, 0.5, 0.66, 0.82, 1], glints: 13, strays: 70, glintDuty: 0.05 }),
  live: true,
  seed: 0xd161,
};

/** apps/digiquant-web/app/_chrome/QuantWordmark.tsx (#4986). The column timing
 *  is lib/hero-build.ts's BUILD_START_MS / BUILD_COLUMN_MS, which the hero chart
 *  sweep also reads. */
export const DIGIQUANT: BannerDefinition = {
  id: "digiquant",
  text: "DIGIQUANT",
  label: "digiquant",
  font: PIXEL_7X10,
  glyphs: {
    A: [".#####.", "#######", "##...##", "##...##", "#######", "#######", "##...##", "##...##", "##...##", "##...##"],
    Q: [".#####.", "#######", "##...##", "##...##", "##...##", "##.#.##", "##..###", "##..###", "#######", ".######"],
  },
  gap: 2,
  palette: {
    ink: INK,
    ground: GROUND,
    up: { hex: "#3DD6C4", cube: 80, cssVar: "--up" },
    down: { hex: "#E5533E", cube: 167, cssVar: "--down" },
    accent: { hex: "#3DD6C4", cube: 80, cssVar: "--accent" },
  },
  animation: riseAnimation({ startMs: 250, columnMs: 16, glintChance: 0.045, strays: 60, glintDuty: 0.06, toneUntil: 0.72 }),
  live: true,
  seed: 0x9a17,
};

/** LOADING timing of packages/ui/src/components/chat/digichat-wordmark.ts. */
export const DIGICHAT_SCRAMBLE: ScrambleOptions = {
  stepMs: 80,
  spinMs: 240,
  lockMs: 180,
  holdMs: 960,
  flashMs: 200,
  settledMs: 2000,
  idleGapMs: 6400,
  pool: "ABCDEFGHIJKLMNOPQRSTUVWXYZ0123456789!?#$%&*+-=/<>().,:;@",
};

/** packages/ui/src/components/chat/digichat-wordmark.ts for LOADING; LIVE is
 *  the streaming-token pass (DIG-2865). */
export const DIGICHAT: BannerDefinition = {
  id: "digichat",
  text: "DIGICHAT",
  label: "digichat",
  font: PIXEL_7X10,
  gap: 2,
  palette: {
    ink: { hex: "#D7D7D7", cube: 188 },
    ground: { hex: "#000000", cube: 16 },
    dim: { hex: "#5F5F5F", cube: 59 },
    rest: { hex: "#D7D7D7", cube: 188 },
    flash: { hex: "#FFFFFF", cube: 231 },
  },
  animation: scrambleAnimation({
    ...DIGICHAT_SCRAMBLE,
    live: { kind: "stream", quietMs: 5200, tokenMs: [70, 190], maxToken: 3 },
  }),
  live: true,
  seed: 0,
};

/** digivoice/tui/src/hero.js (#4965 / #4959) */
export const DIGIVOICE: BannerDefinition = {
  id: "digivoice",
  text: "DIGIVOICE",
  label: "digivoice",
  font: PIXEL_7X10,
  gap: 2,
  palette: {
    ink: { hex: "#FFFFFF", cube: 231 },
    ground: { hex: "#000000", cube: 16 },
    rest: { hex: "#878787", cube: 102 },
    lit: { hex: "#FFFFFF", cube: 231 },
  },
  animation: equalizerAnimation({ buildMs: 1400 }),
  live: true,
  seed: 0,
};

export const BANNERS = { digithings: DIGITHINGS, digiquant: DIGIQUANT, digichat: DIGICHAT, digivoice: DIGIVOICE } as const;
