import { emptyFrame, litCells, mulberry32, setPixel } from "../layout";
import type { Animation, Frame, Layout, Pixel } from "../types";

/**
 * PAGES (digibook). The word is a flipbook.
 * LOADING: `pages` pages turn right to left, one after another and overlapping
 * like a riffle. Each turn is a fold line that leans (the bottom corner leads)
 * with the lifted page, a flap of `accent` paper, curling over the old page
 * just ahead of it. Behind the fold the next page shows. Page k of N carries
 * the lit cells whose seeded rank is below k/N, in faint `accent`; the last
 * page is the whole word in ink, so the riffle draws the word up and the last,
 * slowest turn lays it down.
 * LIVE: a reader. Every so often one page turns over the settled word (the
 * fold in `glint`, a short shadow on the page it uncovers); one in four is a
 * riffle of three quick pages, one in five turns back (left to right).
 */

export type PagesOptions = {
  /** LOADING: number of pages riffled. The last one carries the full word. */
  pages: number;
  /** LOADING: ms each page takes to turn, first to last. Cycled if shorter than `pages`. */
  turnMs: number[];
  /** LOADING: fraction of a turn after which the next page starts (riffle overlap). */
  overlap: number;
  /** Widest the flap (lifted page) gets, in pixels, at mid-turn. */
  curlMax: number;
  /** How far the bottom of the fold leads the top, in pixels. */
  lean: number;
  /** LIVE: ms between page events. */
  everyMs: number;
  /** LIVE: ms for one page turn. */
  liveTurnMs: number;
  /** LIVE: ms between the pages of a riffle. */
  riffleGapMs: number;
};

export type PageTurn = { at: number; ms: number; back: boolean };

export type PagesState = {
  width: number;
  height: number;
  /** Rank of each lit cell in [0, 1); -1 for an empty cell. */
  rank: Float32Array;
  /** LOADING turns, in order. Turn k uncovers page k + 1. */
  turns: PageTurn[];
  seed: number;
  options: PagesOptions;
  ms: number;
};

export function pagesAnimation(options: PagesOptions): Animation<PagesState> {
  return {
    kind: "pages",
    liveTickMs: 40,
    prepare(layout: Layout, def) {
      const { width, height } = layout;
      const rand = mulberry32(def.seed);
      const rank = new Float32Array(width * height).fill(-1);
      for (const cell of litCells(layout)) rank[cell.y * width + cell.x] = rand();
      const turns: PageTurn[] = [];
      let at = 0;
      for (let k = 0; k < options.pages; k += 1) {
        const ms = options.turnMs[k % options.turnMs.length];
        turns.push({ at, ms, back: false });
        at += Math.round(ms * options.overlap);
      }
      const ms = Math.max(...turns.map((turn) => turn.at + turn.ms));
      return { width, height, rank, turns, seed: def.seed, options, ms };
    },
    loadingMs: (state) => state.ms,
    loading,
    live,
    still: settled,
  };
}

/** Ease in and out: the page lifts slowly, crosses fast, settles slowly. */
const ease = (p: number) => (p < 0.5 ? 4 * p * p * p : 1 - (-2 * p + 2) ** 3 / 2);

/** Fold geometry of a turn at progress `p` (0..1), in the turn's own direction
 *  (x counted from the side the page starts on). `edge(y)` is the first column
 *  of the uncovered page; the flap covers the `flap` columns before it. */
function fold(state: PagesState, p: number) {
  const { width, height } = state;
  const { curlMax, lean } = state.options;
  const u = ease(Math.min(1, Math.max(0, p)));
  const from = width + lean;
  const to = -curlMax - 1;
  const base = from - u * (from - to);
  const flap = u > 0 && u < 1 ? Math.max(1, Math.round(curlMax * Math.sin(Math.PI * u))) : 0;
  const edge = (y: number) => Math.round(base - (lean * y) / Math.max(1, height - 1));
  return { edge, flap };
}

type Side = "new" | "flap" | "fold" | "shadow" | "old";

/** Where column `x` of row `y` sits relative to a turn at progress `p`. */
function sideOf(state: PagesState, p: number, back: boolean, x: number, y: number): { side: Side; depth: number } {
  if (p <= 0) return { side: "old", depth: 0 };
  if (p >= 1) return { side: "new", depth: 0 };
  const { edge, flap } = fold(state, p);
  // A forward turn runs right to left; a back turn mirrors it.
  const fx = back ? state.width - 1 - x : x;
  const e = edge(y);
  if (fx >= e) return { side: fx - e < 2 ? "shadow" : "new", depth: fx - e };
  const d = e - 1 - fx;
  if (d === 0 && flap > 0) return { side: "fold", depth: 0 };
  if (d < flap) return { side: "flap", depth: d };
  return { side: "old", depth: 0 };
}

/** Paper of the flap: brightest at the fold, falling off toward its free edge. */
function paper(side: Side, depth: number, flap: number): Pixel {
  if (side === "fold") return { tone: "glint", alpha: 1 };
  return { tone: "accent", alpha: 0.85 - (0.45 * depth) / Math.max(1, flap) };
}

/** Cell (x, y) of LOADING page `k` (0 is blank, `pages` is the full word). */
function pageCell(state: PagesState, k: number, x: number, y: number): Pixel | null {
  const r = state.rank[y * state.width + x];
  if (r < 0 || k <= 0) return null;
  const n = state.options.pages;
  if (k >= n) return { tone: "ink", alpha: 1 };
  if (r >= k / n) return null;
  return { tone: "accent", alpha: 0.3 + (0.35 * k) / n };
}

const dim = (pixel: Pixel | null): Pixel | null => (pixel ? { ...pixel, alpha: pixel.alpha * 0.45 } : null);

function loading(state: PagesState, t: number): Frame {
  const frame = emptyFrame(state.width, state.height);
  for (let y = 0; y < state.height; y += 1) {
    for (let x = 0; x < state.width; x += 1) {
      // The page showing here is the count of turns whose fold has passed it.
      // A flap of an active turn covers whatever is under it.
      let page = 0;
      let top: Pixel | null = null;
      let shadow = false;
      for (const turn of state.turns) {
        const p = (t - turn.at) / turn.ms;
        const { side, depth } = sideOf(state, p, turn.back, x, y);
        if (side === "new" || side === "shadow") page += 1;
        if (side === "shadow") shadow = true;
        if (side === "flap" || side === "fold") top = paper(side, depth, fold(state, p).flap);
      }
      const cell = pageCell(state, page, x, y);
      setPixel(frame, x, y, top ?? (shadow ? dim(cell) : cell));
    }
  }
  return frame;
}

function settled(state: PagesState): Frame {
  const frame = emptyFrame(state.width, state.height);
  for (let i = 0; i < state.rank.length; i += 1) {
    if (state.rank[i] >= 0) frame.pixels[i] = { tone: "ink", alpha: 1 };
  }
  return frame;
}

/** Page event `i` of the LIVE schedule: one turn, or a riffle of three. Seeded
 *  per index, so any moment can be sampled. */
export function liveEvent(state: PagesState, i: number): PageTurn[] {
  const rand = mulberry32((state.seed ^ Math.imul(i + 1, 0x9e3779b1)) >>> 0);
  const { everyMs, liveTurnMs, riffleGapMs } = state.options;
  const at = i * everyMs + Math.floor(rand() * everyMs * 0.4);
  const back = rand() < 1 / 5;
  const count = rand() < 1 / 4 ? 3 : 1;
  return Array.from({ length: count }, (_, k) => ({
    at: at + k * riffleGapMs,
    ms: count > 1 ? Math.round(liveTurnMs * 0.7) : liveTurnMs,
    back,
  }));
}

function live(state: PagesState, tLive: number): Frame {
  const frame = settled(state);
  const { everyMs, liveTurnMs, riffleGapMs } = state.options;
  const span = liveTurnMs + 2 * riffleGapMs;
  const first = Math.max(0, Math.floor((tLive - span) / everyMs) - 1);
  const last = Math.floor(tLive / everyMs);
  for (let i = first; i <= last; i += 1) {
    for (const turn of liveEvent(state, i)) {
      const p = (tLive - turn.at) / turn.ms;
      if (p <= 0 || p >= 1) continue;
      const { flap } = fold(state, p);
      for (let y = 0; y < state.height; y += 1) {
        for (let x = 0; x < state.width; x += 1) {
          const { side, depth } = sideOf(state, p, turn.back, x, y);
          if (side === "flap" || side === "fold") setPixel(frame, x, y, paper(side, depth, flap));
          else if (side === "shadow") setPixel(frame, x, y, dim(frame.pixels[y * state.width + x]));
        }
      }
    }
  }
  return frame;
}
