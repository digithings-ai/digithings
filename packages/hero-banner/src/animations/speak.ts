import { emptyFrame, litCells, mulberry32, setPixel } from "../layout";
import type { Animation, Frame, Layout } from "../types";
import { levelFrac } from "./equalizer";

/**
 * SPEAK (digivoice, DIG-2922). The EQUALIZER grown into a voice meter. Every
 * letter column is a level bar; the word always shows in faint ink above the bar.
 * LOADING (mic check): the faint word fades in, then a sweep runs left to right
 * and each column fills to the top, carrying an accent cap that cools to ink.
 * The last frame is the full word: the settled mark.
 * LIVE: the bars drop from full into speech. Talk comes in syllables, each one
 * louder in one part of the word, with pauses between phrases; accent caps
 * hang over the bars and fall. The column motion is EQUALIZER's `levelFrac`.
 */

export type SpeakOptions = {
  /** Faint word fades in over this. */
  startMs: number;
  /** Sweep from the first column to the last. */
  sweepMs: number;
  /** A column fills bottom to top in this. */
  riseMs: number;
  /** The cap stays accent this long after its column is full. */
  capMs: number;
  /** Alpha of the unlit part of the word. */
  rest: number;
  /** LIVE: the bars fall from full to speech over this. */
  releaseMs: number;
  /** Caps: `peak` hangs over the bar and falls; `tip` lights the bar's top pixel. */
  caps: "peak" | "tip";
  /** A cap holds this long before it falls. */
  holdMs: number;
  /** A cap falls one full column height in this. */
  fallMs: number;
  /** Speech bursts. Off: the bars move like EQUALIZER, without stopping. */
  speech: boolean;
  /** Syllable length range, ms. */
  syllableMs: [number, number];
  /** Syllables in one phrase. */
  phrase: [number, number];
  /** Pause between phrases, ms. */
  pauseMs: [number, number];
  /** Level that stays during a pause. */
  floor: number;
};

type Column = { x: number; ys: number[]; sweepAt: number };
type Syllable = { start: number; end: number; stress: number; centre: number };

export type SpeakState = {
  width: number;
  height: number;
  columns: Column[];
  options: SpeakOptions;
  loadingMs: number;
  syllables: Syllable[];
  cycleMs: number;
};

const STEP_MS = 20;
/** The settled word holds this long before LIVE. */
const SETTLE_MS = 80;
const PHRASES = 8;
const easeOut = (u: number) => 1 - (1 - u) ** 3;
const clamp01 = (v: number) => Math.min(1, Math.max(0, v));

function between(rand: () => number, [lo, hi]: [number, number]): number {
  return lo + (hi - lo) * rand();
}

/** Speech envelope at `t` for a column at `xFrac` (0..1 across the word). */
export function speechLevel(state: SpeakState, t: number, xFrac: number): number {
  const { floor } = state.options;
  const tc = ((t % state.cycleMs) + state.cycleMs) % state.cycleMs;
  for (const s of state.syllables) {
    if (tc < s.start) break;
    if (tc < s.end) {
      const u = (tc - s.start) / (s.end - s.start);
      const shape = Math.sin(Math.PI * u) ** 0.7;
      const formant = 0.6 + 0.4 * Math.exp(-((xFrac - s.centre) ** 2) / (2 * 0.3 ** 2));
      return floor + (1 - floor) * shape * s.stress * formant;
    }
  }
  return floor;
}

/** LIVE bar height in pixels for `column`, before caps. */
function liveReach(state: SpeakState, column: Column, tLive: number, tMount: number): number {
  const n = column.ys.length;
  const eq = levelFrac(column.x, tMount);
  // Speech is the loudness; EQUALIZER only shapes it, so a stressed syllable
  // fills most of a column and a pause empties every one.
  const level = state.options.speech
    ? speechLevel(state, tLive, column.x / Math.max(1, state.width - 1)) * (0.4 + 0.6 * eq)
    : eq;
  const release = Math.max(0, 1 - tLive / state.options.releaseMs) ** 2;
  return Math.max(level, release) * n;
}

/** Peak hold: the highest the bar was, held `holdMs`, then falling. Pure in time. */
function peakReach(state: SpeakState, column: Column, tLive: number, tMount: number): number {
  const { holdMs, fallMs } = state.options;
  const n = column.ys.length;
  let peak = liveReach(state, column, tLive, tMount);
  for (let back = STEP_MS; back <= holdMs + fallMs; back += STEP_MS) {
    if (tLive - back < 0) break;
    const fallen = (Math.max(0, back - holdMs) / fallMs) * n;
    peak = Math.max(peak, liveReach(state, column, tLive - back, tMount - back) - fallen);
  }
  return peak;
}

function drawLoading(state: SpeakState, t: number): Frame {
  const { startMs, riseMs, capMs, rest } = state.options;
  const frame = emptyFrame(state.width, state.height);
  const ghost = rest * clamp01(t / startMs);
  for (const column of state.columns) {
    const n = column.ys.length;
    const since = t - column.sweepAt;
    const reach = since < 0 ? 0 : easeOut(clamp01(since / riseMs)) * n;
    const top = Math.ceil(reach) - 1;
    const capLit = since >= 0 && since < riseMs + capMs;
    column.ys.forEach((y, i) => {
      if (i < reach) setPixel(frame, column.x, y, { tone: capLit && i === top ? "accent" : "ink", alpha: 1 });
      else setPixel(frame, column.x, y, { tone: "ink", alpha: ghost });
    });
  }
  return frame;
}

function drawLive(state: SpeakState, tLive: number, tMount: number): Frame {
  const { rest, caps } = state.options;
  const frame = emptyFrame(state.width, state.height);
  for (const column of state.columns) {
    const n = column.ys.length;
    const reach = liveReach(state, column, tLive, tMount);
    const lit = Math.ceil(reach);
    let cap = -1;
    if (caps === "tip") cap = lit - 1;
    else {
      const peak = Math.min(n - 1, Math.floor(peakReach(state, column, tLive, tMount)));
      if (peak >= lit) cap = peak;
    }
    column.ys.forEach((y, i) => {
      if (i === cap) setPixel(frame, column.x, y, { tone: "accent", alpha: 1 });
      else setPixel(frame, column.x, y, { tone: "ink", alpha: i < reach ? 1 : rest });
    });
  }
  return frame;
}

function drawStill(state: SpeakState): Frame {
  const frame = emptyFrame(state.width, state.height);
  for (const column of state.columns) {
    for (const y of column.ys) setPixel(frame, column.x, y, { tone: "ink", alpha: 1 });
  }
  return frame;
}

export function speakAnimation(options: SpeakOptions): Animation<SpeakState> {
  return {
    kind: "speak",
    liveTickMs: 50,
    prepare(layout: Layout, def) {
      const byX = new Map<number, number[]>();
      for (const cell of litCells(layout)) {
        const ys = byX.get(cell.x) ?? [];
        ys.push(cell.y);
        byX.set(cell.x, ys);
      }
      const span = Math.max(1, layout.width - 1);
      const columns = [...byX.entries()]
        .sort((a, b) => a[0] - b[0])
        .map(([x, ys]) => ({ x, ys: ys.sort((a, b) => b - a), sweepAt: options.startMs + (x / span) * options.sweepMs }));
      const rand = mulberry32(def.seed);
      const syllables: Syllable[] = [];
      let t = 0;
      for (let p = 0; p < PHRASES; p += 1) {
        const count = Math.round(between(rand, options.phrase));
        for (let s = 0; s < count; s += 1) {
          const length = between(rand, options.syllableMs);
          syllables.push({ start: t, end: t + length, stress: 0.7 + 0.3 * rand(), centre: rand() });
          t += length;
        }
        t += between(rand, options.pauseMs);
      }
      const lastSweep = columns.at(-1)?.sweepAt ?? options.startMs;
      return {
        width: layout.width,
        height: layout.height,
        columns,
        options,
        loadingMs: Math.ceil(lastSweep + options.riseMs + options.capMs) + SETTLE_MS,
        syllables,
        cycleMs: t,
      };
    },
    loadingMs: (state) => state.loadingMs,
    loading: drawLoading,
    live: drawLive,
    still: drawStill,
  };
}
