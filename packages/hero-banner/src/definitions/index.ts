import { buildAnimation } from "../animations/build";
import { equalizerAnimation } from "../animations/equalizer";
import { riseAnimation } from "../animations/rise";
import { routeAnimation } from "../animations/route";
import { scrambleAnimation } from "../animations/scramble";
import { typeAnimation } from "../animations/type";
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
  // buildDoneMs: startMs + 78 * columnMs + BUILD_RISE_MS (360) = 1858.
  animation: riseAnimation({
    startMs: 250,
    columnMs: 16,
    glintChance: 0.045,
    strays: 60,
    glintDuty: 0.06,
    toneUntil: 0.72,
    blinkChance: 0.35,
    blinkDuty: 0.03,
    blinkAlpha: 0.35,
    buildDoneMs: 1858,
  }),
  live: true,
  seed: 0x9a17,
};

/** packages/ui/src/components/chat/digichat-wordmark.ts */
export const DIGICHAT: BannerDefinition = {
  id: "digichat",
  text: "DIGICHAT",
  label: "digichat",
  font: PIXEL_7X10,
  gap: 2,
  palette: {
    ink: { hex: "#D7D7D7", cube: 188 }, // canon-allow: a banner palette is renderer data, not a CSS theme; a terminal has no cascade to read a token from
    ground: { hex: "#000000", cube: 16 },
    dim: { hex: "#5F5F5F", cube: 59 }, // canon-allow: a banner palette is renderer data, not a CSS theme; a terminal has no cascade to read a token from
    rest: { hex: "#D7D7D7", cube: 188 }, // canon-allow: a banner palette is renderer data, not a CSS theme; a terminal has no cascade to read a token from
    flash: { hex: "#FFFFFF", cube: 231 }, // canon-allow: a banner palette is renderer data, not a CSS theme; a terminal has no cascade to read a token from
  },
  animation: scrambleAnimation({
    stepMs: 80,
    spinMs: 240,
    lockMs: 180,
    holdMs: 960,
    flashMs: 200,
    settledMs: 2000,
    idleGapMs: 6400,
    pool: "ABCDEFGHIJKLMNOPQRSTUVWXYZ0123456789!?#$%&*+-=/<>().,:;@",
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
    ink: { hex: "#FFFFFF", cube: 231 }, // canon-allow: a banner palette is renderer data, not a CSS theme; a terminal has no cascade to read a token from
    ground: { hex: "#000000", cube: 16 },
    rest: { hex: "#878787", cube: 102 },
    lit: { hex: "#FFFFFF", cube: 231 }, // canon-allow: a banner palette is renderer data, not a CSS theme; a terminal has no cascade to read a token from
  },
  animation: equalizerAnimation({ buildMs: 1400 }),
  live: true,
  seed: 0,
};

/** DIG-2870. A router: one request fans out to every lane (provider) and the
 *  reply comes back. Accent: --accent-digillm. */
export const DIGILLM: BannerDefinition = {
  id: "digillm",
  text: "DIGILLM",
  label: "digillm",
  font: PIXEL_7X10,
  gap: 2,
  palette: {
    ink: INK,
    ground: GROUND,
    accent: { hex: "#B8C95A", cube: 149, cssVar: "--accent-digillm" },
    reply: { hex: "#FFFFFF", cube: 231, cssVar: "--glint" },
  },
  animation: routeAnimation({
    crossMs: 760,
    forkMs: 70,
    jitter: 0.18,
    holdMs: 120,
    returnMs: 520,
    pending: 0.45,
    trail: 7,
    packetEveryMs: 900,
    packetMs: 900,
  }),
  live: true,
  seed: 0x11e1,
};

/** DIG-2876. Typed at a prompt, then built: a block cursor types the word (one
 *  typo, backspaced), parks and blinks, and a build sweep turns the source to
 *  ink. LIVE edits one glyph now and then, or reruns the build. Accent:
 *  --accent-digidev. */
export const DIGIDEV: BannerDefinition = {
  id: "digidev",
  text: "DIGIDEV",
  label: "digidev",
  font: PIXEL_7X10,
  gap: 2,
  palette: {
    ink: INK,
    ground: GROUND,
    accent: { hex: "#6B9DFF", cube: 75, cssVar: "--accent-digidev" },
    glint: { hex: "#FFFFFF", cube: 231, cssVar: "--glint" },
  },
  animation: typeAnimation({
    idleMs: 700,
    keyMs: 130,
    jitter: 0.5,
    typoMs: 380,
    holdMs: 900,
    buildMs: 620,
    blinkMs: 530,
    everyMs: 6000,
  }),
  live: true,
  seed: 0xde7,
};

export const BANNERS = {
  digithings: DIGITHINGS,
  digiquant: DIGIQUANT,
  digichat: DIGICHAT,
  digivoice: DIGIVOICE,
  digillm: DIGILLM,
  digidev: DIGIDEV,
} as const;
