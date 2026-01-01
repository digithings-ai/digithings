import { emptyFrame, litCells, mulberry32, setPixel } from "../layout";
import type { Animation, Frame, Layout, Pixel } from "../types";

/**
 * SPANS (digitrace). The word is a trace waterfall, x is time.
 * LOADING: every pixel row is a lane. Each lane holds a few sibling spans that
 * split the width; a span opens when the clock reaches its left edge (plus a
 * per-lane delay, so lower lanes open later, like children in a waterfall) and
 * grows to the right at its own speed. Inside a span the word shows in ink on a
 * faint `accent` bar, the growing head is `glint`. When a span closes its bar
 * fades, so the staircase of bars drains away and leaves the word.
 * LIVE: requests keep arriving. Now and then a small trace runs over the
 * settled word: a root span on one lane and one to three children on the lanes
 * below, each opening when its parent's head reaches it, nested inside it.
 */

export type SpansOptions = {
  /** LOADING: ms the clock takes to cross one pixel column. */
  colMs: number;
  /** LOADING: extra delay per lane, top to bottom (the waterfall stagger). */
  laneDelayMs: number;
  /** LOADING: sibling spans per lane, [min, max]. */
  siblings: [number, number];
  /** LOADING: span speed spread; each span runs at colMs × a factor in this range. */
  speed: [number, number];
  /** ms a closed span's bar takes to fade. */
  fadeMs: number;
  /** Bar alpha on empty cells, even and odd lanes. */
  barAlpha: [number, number];
  /** LIVE: ms between traces. */
  everyMs: number;
  /** LIVE: ms per pixel column for a LIVE span head. */
  liveColMs: number;
};

export type Span = {
  lane: number;
  /** First and last-plus-one column. */
  a: number;
  b: number;
  /** ms the span opens and closes. */
  open: number;
  close: number;
};

export type SpansState = {
  width: number;
  height: number;
  lit: Uint8Array;
  spans: Span[];
  seed: number;
  options: SpansOptions;
  ms: number;
};

export function spansAnimation(options: SpansOptions): Animation<SpansState> {
  return {
    kind: "spans",
    liveTickMs: 40,
    prepare(layout: Layout, def) {
      const { width, height } = layout;
      const rand = mulberry32(def.seed);
      const lit = new Uint8Array(width * height);
      for (const cell of litCells(layout)) lit[cell.y * width + cell.x] = 1;
      const [lo, hi] = options.siblings;
      const spans: Span[] = [];
      for (let lane = 0; lane < height; lane += 1) {
        const n = lo + Math.floor(rand() * (hi - lo + 1));
        // n - 1 cut points, each kept clear of the edges and each other.
        const cuts = Array.from({ length: n - 1 }, () => Math.round(width * (0.15 + 0.7 * rand()))).sort((p, q) => p - q);
        const edges = [0, ...cuts, width].filter((x, i, all) => i === 0 || x - all[i - 1] >= 4 || x === width);
        for (let j = 0; j + 1 < edges.length; j += 1) {
          const a = edges[j];
          const b = edges[j + 1];
          const factor = options.speed[0] + rand() * (options.speed[1] - options.speed[0]);
          const open = Math.round(lane * options.laneDelayMs + a * options.colMs);
          spans.push({ lane, a, b, open, close: open + Math.round((b - a) * options.colMs * factor) });
        }
      }
      const ms = Math.max(...spans.map((s) => s.close)) + options.fadeMs;
      return { width, height, lit, spans, seed: def.seed, options, ms };
    },
    loadingMs: (state) => state.ms,
    loading,
    live,
    still: settled,
  };
}

/** Column the head of `span` has reached at `t`; `b` once it has closed. */
const head = (span: Span, t: number) =>
  t >= span.close ? span.b : span.a + Math.floor(((t - span.open) / (span.close - span.open)) * (span.b - span.a));

/** Paint `span` at `t` into `frame`. Empty cells get the bar, lit cells ink,
 *  the head column glint. A closed span's bar fades over `fadeMs`. */
function paintSpan(state: SpansState, frame: Frame, span: Span, t: number): void {
  if (t < span.open) return;
  const { width, lit, options } = state;
  const y = span.lane;
  const h = head(span, t);
  const fade = t <= span.close ? 1 : Math.max(0, 1 - (t - span.close) / options.fadeMs);
  const bar = options.barAlpha[y % 2] * fade;
  for (let x = span.a; x < h && x < span.b; x += 1) {
    const on = lit[y * width + x] === 1;
    let pixel: Pixel | null = on ? { tone: "ink", alpha: 1 } : bar > 0.02 ? { tone: "accent", alpha: bar } : null;
    if (t < span.close && x === h - 1) pixel = { tone: "glint", alpha: on ? 1 : 0.6 };
    if (pixel) setPixel(frame, x, y, pixel);
  }
}

function loading(state: SpansState, t: number): Frame {
  const frame = emptyFrame(state.width, state.height);
  for (const span of state.spans) paintSpan(state, frame, span, t);
  return frame;
}

function settled(state: SpansState): Frame {
  const frame = emptyFrame(state.width, state.height);
  for (let i = 0; i < state.lit.length; i += 1) if (state.lit[i]) frame.pixels[i] = { tone: "ink", alpha: 1 };
  return frame;
}

/** LIVE trace `i`: a root span and its children, seeded per index so any
 *  moment can be sampled. Children sit on the lanes below the root, nest
 *  inside its columns and open when the root's head reaches them. */
export function liveTrace(state: SpansState, i: number): Span[] {
  const rand = mulberry32((state.seed ^ Math.imul(i + 1, 0x9e3779b1)) >>> 0);
  const { width, height, options } = state;
  const { everyMs, liveColMs } = options;
  const at = i * everyMs + Math.floor(rand() * everyMs * 0.4);
  const kids = 1 + Math.floor(rand() * 3);
  const lane = Math.floor(rand() * Math.max(1, height - kids));
  const len = Math.round(width * (0.35 + 0.4 * rand()));
  const a = Math.floor(rand() * (width - len));
  const root: Span = { lane, a, b: a + len, open: at, close: at + len * liveColMs };
  const trace = [root];
  let from = a;
  for (let k = 1; k <= kids; k += 1) {
    const ca = Math.min(root.b - 3, from + 1 + Math.floor(rand() * len * 0.3));
    const cb = Math.min(root.b, ca + 3 + Math.floor(rand() * (root.b - ca - 3)));
    const open = at + (ca - a) * liveColMs;
    trace.push({ lane: lane + k, a: ca, b: cb, open, close: open + Math.round((cb - ca) * liveColMs * 1.3) });
    from = ca;
  }
  return trace;
}

function live(state: SpansState, tLive: number): Frame {
  const frame = settled(state);
  const { everyMs, fadeMs, liveColMs } = state.options;
  const span = state.width * liveColMs * 1.3 + fadeMs;
  const first = Math.max(0, Math.floor((tLive - span) / everyMs) - 1);
  const last = Math.floor(tLive / everyMs);
  for (let i = first; i <= last; i += 1) {
    for (const s of liveTrace(state, i)) if (tLive < s.close + fadeMs) paintSpan(state, frame, s, tLive);
  }
  return frame;
}
