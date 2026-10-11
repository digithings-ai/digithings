import { buildAnimation } from "../animations/build";
import { equalizerAnimation } from "../animations/equalizer";
import { pagesAnimation } from "../animations/pages";
import { riseAnimation } from "../animations/rise";
import { routeAnimation } from "../animations/route";
import { scrambleAnimation } from "../animations/scramble";
import { stackAnimation } from "../animations/stack";
import { traverseAnimation } from "../animations/traverse";
import { tumblerAnimation } from "../animations/tumbler";
import { speakAnimation, type SpeakOptions } from "../animations/speak";
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

/** The baseline: digivoice/tui/src/hero.js (#4965 / #4959), ported frame for
 *  frame (test/parity.test.ts). DIGIVOICE replaces it on every surface; it
 *  stays until the digivoice TUI, Python and Lua heroes move onto the package. */
export const DIGIVOICE_BASELINE: BannerDefinition = {
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

const SPEAK = {
  startMs: 220,
  sweepMs: 820,
  riseMs: 200,
  capMs: 240,
  rest: 0.3,
  releaseMs: 520,
  caps: "peak",
  holdMs: 300,
  fallMs: 700,
  speech: true,
  syllableMs: [130, 260],
  phrase: [3, 7],
  pauseMs: [420, 1100],
  floor: 0.08,
} satisfies SpeakOptions;

/** DIG-2922. digivoice is a voice: the EQUALIZER becomes a voice meter. Each
 *  letter column is a level bar, speech comes in syllables and phrases, and
 *  accent peak caps hang over the bars. Accent: --accent-digivoice. */
export const DIGIVOICE: BannerDefinition = {
  id: "digivoice",
  text: "DIGIVOICE",
  label: "digivoice",
  font: PIXEL_7X10,
  gap: 2,
  palette: { ink: INK, ground: GROUND, accent: { hex: "#CF6BD6", cube: 170, cssVar: "--accent-digivoice" } },
  animation: speakAnimation(SPEAK),
  live: true,
  seed: 0x5e1c,
};

/** The variations explored before DIGIVOICE (SPEECH) was locked, kept for the
 *  review previews: LEVEL lights the top of a non-stop bar, PEAK adds the
 *  falling caps without speech. */
export const DIGIVOICE_VARIANTS = {
  "digivoice-level": { ...DIGIVOICE, animation: speakAnimation({ ...SPEAK, caps: "tip", speech: false }) },
  "digivoice-peak": { ...DIGIVOICE, animation: speakAnimation({ ...SPEAK, speech: false }) },
} satisfies Record<string, BannerDefinition>;

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

/** DIG-2869. A table filling up: records drop in row by row from the bottom,
 *  land written (accent) and commit to ink a row at a time. Accent:
 *  --accent-digibase. */
export const DIGIBASE: BannerDefinition = {
  id: "digibase",
  text: "DIGIBASE",
  label: "digibase",
/** DIG-2868. A pin-tumbler lock: a key slides in along the shear line, every
 *  pin drops into line as the tip passes, then the key turns. Accent: --accent-digikey. */
export const DIGIKEY: BannerDefinition = {
  id: "digikey",
  text: "DIGIKEY",
  label: "digikey",
/** DIG-2878. A flipbook: pages riffle right to left, each carrying more of the
 *  word, and the last, slowest turn lays it down in ink. LIVE turns a page now
 *  and then. Accent: --accent-digibook. */
export const DIGIBOOK: BannerDefinition = {
  id: "digibook",
  text: "DIGIBOOK",
  label: "digibook",
  font: PIXEL_7X10,
  gap: 2,
  palette: {
    ink: INK,
    ground: GROUND,
    accent: { hex: "#9EA0A5", cube: 247, cssVar: "--accent-digibase" },
    glint: { hex: "#FFFFFF", cube: 231, cssVar: "--glint" },
  },
  animation: stackAnimation({
    rowMs: 120,
    sweepMs: 260,
    fallMs: 420,
    blockMax: 4,
    holdMs: 60,
    commitMs: 260,
    txEveryMs: 1100,
    txWriteMs: 520,
    scanMs: 900,
  }),
  live: true,
  seed: 0xdb05,
    accent: { hex: "#D97A5A", cube: 173, cssVar: "--accent-digikey" },
    glint: { hex: "#FFFFFF", cube: 231, cssVar: "--glint" },
  },
  animation: tumblerAnimation({
    keyMs: 1300,
    settleMs: 200,
    clickMs: 90,
    holdMs: 160,
    turnMs: 420,
    maxOffset: 3,
    locked: 0.32,
    eventEveryMs: 2200,
    pickMs: 360,
  }),
  live: true,
  seed: 0x6e7,
};

/** DIG-2867. A workflow graph: a run floods along each letter's strokes,
 *  branching at forks, flashes every task it reaches and hops the gap into the
 *  next letter. Accent: --accent-digigraph. */
export const DIGIGRAPH: BannerDefinition = {
  id: "digigraph",
  text: "DIGIGRAPH",
  label: "digigraph",
  font: PIXEL_7X10,
  gap: 2,
  palette: {
    ink: INK,
    ground: GROUND,
    accent: { hex: "#E5B765", cube: 179, cssVar: "--accent-digigraph" },
    glint: { hex: "#FFFFFF", cube: 231, cssVar: "--glint" },
  },
  animation: traverseAnimation({
    startMs: 200,
    stepMs: 16,
    hopMs: 70,
    frontMs: 90,
    trailMs: 140,
    taskMs: 160,
    holdMs: 240,
    blueprint: 0.16,
    runEveryMs: 1800,
    sprint: 0.5,
  }),
  live: true,
  seed: 0xd16a,
    accent: { hex: "#D4C5A0", cube: 187, cssVar: "--accent-digibook" },
    glint: { hex: "#FFFFFF", cube: 231, cssVar: "--glint" },
  },
  animation: pagesAnimation({
    pages: 5,
    turnMs: [420, 340, 300, 360, 720],
    overlap: 0.55,
    curlMax: 7,
    lean: 4,
    everyMs: 5200,
    liveTurnMs: 900,
    riffleGapMs: 260,
  }),
  live: true,
  seed: 0xb00c,
};

export const BANNERS = {
  digithings: DIGITHINGS,
  digiquant: DIGIQUANT,
  digichat: DIGICHAT,
  digivoice: DIGIVOICE,
  digillm: DIGILLM,
  digibase: DIGIBASE,
  digikey: DIGIKEY,
  digigraph: DIGIGRAPH,
  digibook: DIGIBOOK,
} as const;
