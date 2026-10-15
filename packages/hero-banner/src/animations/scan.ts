import { emptyFrame, litCells, mulberry32, setPixel } from "../layout";
import type { Animation, Frame, Layout, Pixel } from "../types";

/**
 * SCAN (digisearch). The word is found, not drawn.
 * LOADING: the word sits hidden in an index, a field of faint `accent` decoy
 * pixels where its own cells look no different from the noise. A scan beam
 * (`glint`, the full height) sweeps left to right. Where it has passed, the
 * decoys drop out and the word's cells are hits: bright `accent` in a short
 * highlight band behind the beam, then `ink`. The beam leaves the word settled.
 * LIVE: queries. Every so often a fainter beam sweeps a query over the settled
 * word; every glyph run that matches it lights up in `accent` on a soft marker
 * band while the rest dims, holds, then clears. The first query is "SEARCH";
 * the rest are seeded substrings of the text, so a repeated letter gets more
 * than one hit.
 */

export type ScanOptions = {
  /** LOADING: ms for the beam to cross the word and its highlight band. */
  sweepMs: number;
  /** LOADING: share of empty cells that hold a decoy pixel. */
  noise: number;
  /** Columns of highlight band behind the beam. */
  trail: number;
  /** LIVE: ms between queries. */
  everyMs: number;
  /** LIVE: ms for a query beam to cross the word. */
  liveSweepMs: number;
  /** LIVE: ms the hits hold after the beam has crossed. */
  holdMs: number;
  /** LIVE: ms the dimmed non-matches take to come back. */
  fadeMs: number;
  /** LIVE: longest seeded query, in letters. */
  maxQuery: number;
};

export type Query = { at: number; text: string; hits: boolean[] };

export type ScanState = {
  width: number;
  height: number;
  text: string;
  /** Glyph index of each lit cell; -1 for an empty cell. */
  glyph: Int8Array;
  /** Decoy brightness in (0, 1] for a decoy cell, 0 otherwise. Lit cells get one too: they hide in the noise. */
  decoy: Float32Array;
  /** First and one-past-last column of each glyph. */
  spans: [number, number][];
  seed: number;
  options: ScanOptions;
};

export function scanAnimation(options: ScanOptions): Animation<ScanState> {
  return {
    kind: "scan",
    liveTickMs: 40,
    prepare(layout: Layout, def) {
      const { width, height, text, font, starts } = layout;
      const rand = mulberry32(def.seed);
      const glyph = new Int8Array(width * height).fill(-1);
      for (const cell of litCells(layout)) glyph[cell.y * width + cell.x] = cell.glyph;
      const decoy = new Float32Array(width * height);
      for (let i = 0; i < decoy.length; i += 1) {
        const r = rand();
        if (glyph[i] >= 0 || r < options.noise) decoy[i] = 0.35 + 0.65 * rand();
      }
      const spans = starts.map((x): [number, number] => [x, x + font.cols]);
      return { width, height, text, glyph, decoy, spans, seed: def.seed, options };
    },
    loadingMs: (state) => state.options.sweepMs,
    loading,
    live,
    still: settled,
  };
}

/** Gentle ease in and out: the beam picks up, scans steadily, slows to a stop. */
const ease = (p: number) => 0.5 - Math.cos(Math.PI * Math.min(1, Math.max(0, p))) / 2;

const INK: Pixel = { tone: "ink", alpha: 1 };
const HIT: Pixel = { tone: "accent", alpha: 1 };

/** Beam column at progress `p`: from just left of the word to past its highlight band. */
function beamAt(state: ScanState, p: number): number {
  return -1 + p * (state.width + state.options.trail + 1);
}

function loading(state: ScanState, t: number): Frame {
  const { width, height, glyph, decoy } = state;
  const { trail } = state.options;
  const frame = emptyFrame(width, height);
  const beam = beamAt(state, ease(t / state.options.sweepMs));
  for (let y = 0; y < height; y += 1) {
    for (let x = 0; x < width; x += 1) {
      const i = y * width + x;
      const lit = glyph[i] >= 0;
      const d = beam - x;
      let pixel: Pixel | null = null;
      if (d < 0) {
        // Ahead of the beam: the index, word and decoys alike.
        if (decoy[i] > 0) pixel = { tone: "accent", alpha: 0.1 + 0.18 * decoy[i] };
      } else if (d < 1) {
        pixel = { tone: "glint", alpha: lit ? 1 : 0.4 };
      } else if (d < trail + 1) {
        // The highlight band: hits bright, a faint marker behind them, decoys gone.
        pixel = lit ? HIT : { tone: "accent", alpha: 0.16 * (1 - (d - 1) / trail) };
      } else if (lit) {
        pixel = INK;
      }
      setPixel(frame, x, y, pixel);
    }
  }
  return frame;
}

function settled(state: ScanState): Frame {
  const frame = emptyFrame(state.width, state.height);
  for (let i = 0; i < state.glyph.length; i += 1) if (state.glyph[i] >= 0) frame.pixels[i] = INK;
  return frame;
}

/** Glyphs covered by an occurrence of `query` in `text`. */
export function matches(text: string, query: string): boolean[] {
  const hits = Array.from(text, () => false);
  for (let i = text.indexOf(query); i >= 0; i = text.indexOf(query, i + 1)) {
    for (let k = 0; k < query.length; k += 1) hits[i + k] = true;
  }
  return hits;
}

/** Query `i` of the LIVE schedule. Seeded per index, so any moment can be sampled. */
export function liveQuery(state: ScanState, i: number): Query {
  const rand = mulberry32((state.seed ^ Math.imul(i + 1, 0x9e3779b1)) >>> 0);
  const { everyMs, maxQuery } = state.options;
  const at = i * everyMs + Math.floor(rand() * everyMs * 0.3);
  let text = "SEARCH";
  if (i > 0 || !state.text.includes(text)) {
    const len = 1 + Math.floor(rand() * Math.min(maxQuery, state.text.length));
    const start = Math.floor(rand() * (state.text.length - len + 1));
    text = state.text.slice(start, start + len);
  }
  return { at, text, hits: matches(state.text, text) };
}

function live(state: ScanState, tLive: number): Frame {
  const frame = settled(state);
  const { width, height, glyph, spans } = state;
  const { everyMs, liveSweepMs, holdMs, fadeMs } = state.options;
  const q = liveQuery(state, Math.floor(tLive / everyMs));
  const te = tLive - q.at;
  if (te < 0 || te >= liveSweepMs + holdMs + fadeMs) return frame;
  const beam = te < liveSweepMs ? -1 + (te / liveSweepMs) * (width + 1) : width;
  // Non-matches dim behind the beam, then come back over `fadeMs`.
  const back = Math.max(0, (te - liveSweepMs - holdMs) / fadeMs);
  const dimmed: Pixel = { tone: "ink", alpha: 0.45 + 0.55 * back };
  const showHits = te < liveSweepMs + holdMs;
  for (let y = 0; y < height; y += 1) {
    for (let x = 0; x < width; x += 1) {
      const i = y * width + x;
      const g = glyph[i];
      const d = beam - x;
      if (d >= 0 && d < 1) {
        setPixel(frame, x, y, { tone: "glint", alpha: g >= 0 ? 1 : 0.25 });
        continue;
      }
      if (d < 0) continue;
      if (g >= 0) {
        setPixel(frame, x, y, q.hits[g] && showHits ? HIT : q.hits[g] ? INK : dimmed);
      } else if (showHits) {
        // The marker: a soft band under each hit glyph.
        const span = spans.findIndex(([a, b]) => x >= a && x < b);
        if (span >= 0 && q.hits[span]) setPixel(frame, x, y, { tone: "accent", alpha: 0.14 });
      }
    }
  }
  return frame;
}
