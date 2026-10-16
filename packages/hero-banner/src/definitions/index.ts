import { buildAnimation } from "../animations/build";
import { equalizerAnimation } from "../animations/equalizer";
import { riseAnimation } from "../animations/rise";
import { routeAnimation } from "../animations/route";
import { scrambleAnimation, type ScrambleOptions } from "../animations/scramble";
import { stackAnimation } from "../animations/stack";
import { tumblerAnimation } from "../animations/tumbler";
import { traverseAnimation } from "../animations/traverse";
import { pagesAnimation } from "../animations/pages";
import { typeAnimation } from "../animations/type";
import { clawAnimation, withHeadroom } from "../animations/claw";
import { vaultAnimation } from "../animations/vault";
import { scanAnimation } from "../animations/scan";
import { spansAnimation } from "../animations/spans";
import { fetchAnimation } from "../animations/fetch";
import { speakAnimation, type SpeakOptions } from "../animations/speak";
import { PIXEL_7X10 } from "../font";
import type { BannerDefinition, Tone } from "../types";

/**
 * Module banners. Each definition is the single source for its TUI and web
 * marks. The four originally ported marks (digithings, digiquant, digichat,
 * and the digivoice equalizer baseline) keep the legacy timings and seeds so
 * the port draws the same cells (see test/parity.test.ts). DIGIVOICE_BASELINE
 * stays out of BANNERS; the shipped digivoice mark is speakAnimation.
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
    ink: { hex: "#D7D7D7", cube: 188 }, // canon-allow: a banner palette is renderer data, not a CSS theme; a terminal has no cascade to read a token from
    ground: { hex: "#000000", cube: 16 },
    dim: { hex: "#5F5F5F", cube: 59 }, // canon-allow: a banner palette is renderer data, not a CSS theme; a terminal has no cascade to read a token from
    rest: { hex: "#D7D7D7", cube: 188 }, // canon-allow: a banner palette is renderer data, not a CSS theme; a terminal has no cascade to read a token from
    flash: { hex: "#FFFFFF", cube: 231 }, // canon-allow: a banner palette is renderer data, not a CSS theme; a terminal has no cascade to read a token from
  },
  animation: scrambleAnimation({
    ...DIGICHAT_SCRAMBLE,
    live: { kind: "stream", quietMs: 5200, tokenMs: [70, 190], maxToken: 3 },
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
};

/** DIG-2868. A pin-tumbler lock: a key slides in along the shear line, every
 *  pin drops into line as the tip passes, then the key turns. Accent: --accent-digikey. */
export const DIGIKEY: BannerDefinition = {
  id: "digikey",
  text: "DIGIKEY",
  label: "digikey",
  font: PIXEL_7X10,
  gap: 2,
  palette: {
    ink: INK,
    ground: GROUND,
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
};

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

/** DIG-2875. An arcade claw machine picks the word out of a pile: the claw
 *  travels a faint rail, drops, grips each sunk glyph and lifts it into place
 *  (one seeded grab slips and is retried). LIVE plucks one glyph now and then
 *  and sets it back, or lets it slip. The font carries four blank rows of
 *  headroom for the gantry. Accent: --accent-digiclaw. */
export const DIGICLAW: BannerDefinition = {
  id: "digiclaw",
  text: "DIGICLAW",
  label: "digiclaw",
  font: withHeadroom(PIXEL_7X10),
  gap: 2,
  palette: {
    ink: INK,
    ground: GROUND,
    accent: { hex: "#B87840", cube: 137, cssVar: "--accent-digiclaw" },
    glint: { hex: "#FFFFFF", cube: 231, cssVar: "--glint" },
  },
  animation: clawAnimation({
    enterMs: 260,
    travelMs: 110,
    dropMs: 140,
    gripMs: 60,
    liftMs: 200,
    releaseMs: 50,
    flashMs: 140,
    paceStart: 1.05,
    paceMin: 0.5,
    exitMs: 280,
    everyMs: 7000,
  }),
  live: true,
  seed: 0xc1a3,
};

/** DIG-2874. The vault door opens: a combination dial turns right, left, right,
 *  the bolts slide back, the leaves part from the seam and the word inside
 *  lights up. LIVE: a scan line runs down the word, or the bolts relock and
 *  draw back. Accent: --accent-digivault. */
export const DIGIVAULT: BannerDefinition = {
  id: "digivault",
  text: "DIGIVAULT",
  label: "digivault",
  font: PIXEL_7X10,
  gap: 2,
  palette: {
    ink: INK,
    ground: GROUND,
    accent: { hex: "#9D8FC9", cube: 140, cssVar: "--accent-digivault" },
    glint: { hex: "#FFFFFF", cube: 231, cssVar: "--glint" },
  },
  animation: vaultAnimation({ turnMs: 560, boltMs: 380, openMs: 720, settleMs: 520, everyMs: 7000, scanMs: 900 }),
  live: true,
  seed: 0xdb17,
};

/** DIG-2873. A search: the word hides in an index of decoy pixels until a scan
 *  beam finds it. LIVE runs queries over it and highlights the hits.
 *  Accent: --accent-digisearch. */
export const DIGISEARCH: BannerDefinition = {
  id: "digisearch",
  text: "DIGISEARCH",
  label: "digisearch",
  font: PIXEL_7X10,
  gap: 2,
  palette: {
    ink: INK,
    ground: GROUND,
    accent: { hex: "#5AA3C4", cube: 74, cssVar: "--accent-digisearch" },
    glint: { hex: "#FFFFFF", cube: 231, cssVar: "--glint" },
  },
  animation: scanAnimation({
    sweepMs: 1700,
    noise: 0.55,
    trail: 8,
    everyMs: 6000,
    liveSweepMs: 900,
    holdMs: 1400,
    fadeMs: 350,
    maxQuery: 4,
  }),
  live: true,
  seed: 0x5ea2c,
};

/** DIG-2872. A trace waterfall, x is time: each pixel row is a lane of
 *  sibling spans that open in a staircase and grow right, the word in ink on
 *  their bars; the bars drain and leave the word. LIVE runs a small trace
 *  (root plus children) now and then. Accent: --accent-digitrace. */
export const DIGITRACE: BannerDefinition = {
  id: "digitrace",
  text: "DIGITRACE",
  label: "digitrace",
  font: PIXEL_7X10,
  gap: 2,
  palette: {
    ink: INK,
    ground: GROUND,
    accent: { hex: "#6FA3A3", cube: 73, cssVar: "--accent-digitrace" },
    glint: { hex: "#FFFFFF", cube: 231, cssVar: "--glint" },
  },
  animation: spansAnimation({
    colMs: 14,
    laneDelayMs: 70,
    siblings: [2, 4],
    speed: [0.7, 1.5],
    fadeMs: 520,
    barAlpha: [0.34, 0.24],
    everyMs: 4200,
    liveColMs: 16,
  }),
  live: true,
  seed: 0x7ace,
};

/** DIG-2871. A download, not a drawing: a request pixel runs out of the right
 *  edge, then every lit cell comes back as a packet streamed in from the right
 *  along its row and lands with a glint. LIVE fetches again now and then: a
 *  request on one row, a small burst of packets back. Accent: --accent-digifetch. */
export const DIGIFETCH: BannerDefinition = {
  id: "digifetch",
  text: "DIGIFETCH",
  label: "digifetch",
  font: PIXEL_7X10,
  gap: 2,
  palette: {
    ink: INK,
    ground: GROUND,
    accent: { hex: "#C9A45C", cube: 179, cssVar: "--accent-digifetch" },
    glint: { hex: "#FFFFFF", cube: 231, cssVar: "--glint" },
  },
  animation: fetchAnimation({
    requestColMs: 8,
    packetColMs: 5,
    launchColMs: 18,
    jitterMs: 16,
    flashMs: 140,
    tail: [0.5, 0.2],
    everyMs: 3800,
    burst: [4, 7],
  }),
  live: true,
  seed: 0xfe7c,
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
  digidev: DIGIDEV,
  digiclaw: DIGICLAW,
  digivault: DIGIVAULT,
  digisearch: DIGISEARCH,
  digitrace: DIGITRACE,
  digifetch: DIGIFETCH,
} as const;
