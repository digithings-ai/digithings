import { emptyFrame, litCells, mulberry32, setPixel } from "../layout";
import type { Animation, Frame, Layout, Pixel } from "../types";

/**
 * TRAVERSE (digigraph). The word is a workflow graph: every letter is a node,
 * its strokes are the edges a run walks, and its dead ends are the tasks.
 * LOADING: the graph starts as a blueprint (dim strokes, dim accent tasks).
 * A run enters the first letter at its left edge and floods along the strokes,
 * one pixel per step, branching wherever a stroke forks. The front is accent;
 * behind it the stroke sets as ink. A task flashes `glint` as the run reaches
 * it. When the front reaches a letter's right edge, a hop edge carries the run
 * across the gap into the next letter, while the branches still running in the
 * first one finish in parallel. The hop edges stay drawn until the graph is
 * done, then fade with the blueprint.
 * LIVE: the word stays put. Now and then a run enters a letter and walks one to
 * three letters as a thin accent front with glints on the tasks. One run in
 * four walks the whole word, faster.
 */

export type TraverseOptions = {
  /** Pause before the run enters the first letter. */
  startMs: number;
  /** ms per pixel step along a stroke. */
  stepMs: number;
  /** ms for the run to cross a hop edge between letters. */
  hopMs: number;
  /** ms a pixel stays accent once the front reaches it. */
  frontMs: number;
  /** ms a reached stroke shows half ink before it sets. */
  trailMs: number;
  /** ms a task glints when the run reaches it. */
  taskMs: number;
  /** Pause after the last task before the blueprint fades. */
  holdMs: number;
  /** Strength of a stroke the run has not reached yet. */
  blueprint: number;
  /** LIVE: ms between runs. */
  runEveryMs: number;
  /** LIVE: step time of a whole-word run, as a fraction of `stepMs`. */
  sprint: number;
};

type Cell = { x: number; y: number; glyph: number; dist: number; task: boolean };

export type TraverseState = {
  width: number;
  height: number;
  cells: Cell[];
  glyphs: number;
  /** Steps from a letter's entry to its exit, per letter. */
  exitDist: number[];
  /** Hop edge from letter g to g + 1, as gap pixels in walk order. */
  hops: { x: number; y: number }[][];
  seed: number;
  options: TraverseOptions;
  ms: number;
};

const ACCENT: Pixel = { tone: "accent", alpha: 1 };
const GLINT: Pixel = { tone: "glint", alpha: 1 };
const INK: Pixel = { tone: "ink", alpha: 1 };
const HALF: Pixel = { tone: "ink", alpha: 0.55 };

export function traverseAnimation(options: TraverseOptions): Animation<TraverseState> {
  return {
    kind: "traverse",
    liveTickMs: 40,
    prepare(layout: Layout, def) {
      const all = litCells(layout);
      const cells: Cell[] = [];
      const exitDist: number[] = [];
      const entries: Cell[] = [];
      const exits: Cell[] = [];
      for (let g = 0; g < layout.starts.length; g += 1) {
        const mine = all.filter((c) => c.glyph === g).map((c) => ({ ...c, dist: -1, task: false }));
        const mid = (layout.height - 1) / 2;
        const nearMid = (a: Cell, b: Cell) => Math.abs(a.y - mid) - Math.abs(b.y - mid) || a.y - b.y;
        const minX = Math.min(...mine.map((c) => c.x));
        const maxX = Math.max(...mine.map((c) => c.x));
        const entry = mine.filter((c) => c.x === minX).sort(nearMid)[0]!;
        walk(mine, entry);
        // The exit is the right-edge pixel the run reaches first.
        const exit = mine.filter((c) => c.x === maxX && c.dist >= 0).sort((a, b) => a.dist - b.dist || nearMid(a, b))[0]!;
        entries.push(entry);
        exits.push(exit);
        exitDist.push(exit.dist);
        cells.push(...mine.filter((c) => c.dist >= 0));
      }
      const hops: { x: number; y: number }[][] = [];
      for (let g = 0; g + 1 < layout.starts.length; g += 1) hops.push(hopPath(exits[g]!, entries[g + 1]!));
      const state: TraverseState = {
        width: layout.width,
        height: layout.height,
        cells,
        glyphs: layout.starts.length,
        exitDist,
        hops,
        seed: def.seed,
        options,
        ms: 0,
      };
      const last = Math.max(...cells.map((c) => reach(state, c.glyph, c.dist, options.startMs, options.stepMs)));
      state.ms = last + Math.max(options.frontMs + options.trailMs, options.taskMs) + options.holdMs;
      return state;
    },
    loadingMs: (state) => state.ms,
    loading,
    live,
    still: settled,
  };
}

/** 4-connected breadth-first walk from `entry`; a cell no step leads on from is a task. */
function walk(cells: Cell[], entry: Cell): void {
  const at = new Map(cells.map((c) => [`${c.x},${c.y}`, c]));
  entry.dist = 0;
  const queue = [entry];
  for (let i = 0; i < queue.length; i += 1) {
    const c = queue[i]!;
    for (const [dx, dy] of [[1, 0], [0, 1], [0, -1], [-1, 0]] as const) {
      const n = at.get(`${c.x + dx},${c.y + dy}`);
      if (n && n.dist < 0) {
        n.dist = c.dist + 1;
        queue.push(n);
      }
    }
  }
  for (const c of cells) {
    if (c.dist < 0) continue;
    const next = [[1, 0], [0, 1], [0, -1], [-1, 0]].some(([dx, dy]) => at.get(`${c.x + dx!},${c.y + dy!}`)?.dist === c.dist + 1);
    c.task = !next && c.dist > 0;
  }
}

/** Gap pixels from `exit` to `entry`: down or up the first gap column, then across.
 *  The first gap column survives a narrow terminal's gap of 1. */
function hopPath(exit: Cell, entry: Cell): { x: number; y: number }[] {
  const path: { x: number; y: number }[] = [];
  const x0 = exit.x + 1;
  const dir = Math.sign(entry.y - exit.y);
  for (let y = exit.y; y !== entry.y; y += dir) path.push({ x: x0, y });
  for (let x = x0; x < entry.x; x += 1) path.push({ x, y: entry.y });
  return path;
}

/** When a run that entered letter `from` at `start` reaches step `dist` of letter `g`. */
function reach(state: TraverseState, g: number, dist: number, start: number, step: number, from = 0): number {
  let t = start;
  for (let k = from; k < g; k += 1) t += state.exitDist[k]! * step + state.options.hopMs;
  return t + dist * step;
}

function settled(state: TraverseState): Frame {
  const frame = emptyFrame(state.width, state.height);
  for (const c of state.cells) setPixel(frame, c.x, c.y, INK);
  return frame;
}

/** Paint the hop edge from letter `g` to `g + 1`, `p` of the way across. */
function paintHop(state: TraverseState, frame: Frame, g: number, p: number, rest: Pixel | null): void {
  const path = state.hops[g]!;
  const head = Math.floor(p * path.length);
  path.forEach((px, i) => {
    if (i < head) setPixel(frame, px.x, px.y, rest);
    else if (i === head && p < 1) setPixel(frame, px.x, px.y, ACCENT);
  });
}

function loading(state: TraverseState, t: number): Frame {
  const frame = emptyFrame(state.width, state.height);
  const { startMs, stepMs, hopMs, frontMs, trailMs, taskMs, blueprint } = state.options;
  const fade = Math.min(1, Math.max(0, (t - (state.ms - state.options.holdMs)) / state.options.holdMs));

  for (let g = 0; g + 1 < state.glyphs; g += 1) {
    const leave = reach(state, g, state.exitDist[g]!, startMs, stepMs);
    if (t < leave) continue;
    const alpha = 0.4 * (1 - fade);
    paintHop(state, frame, g, Math.min(1, (t - leave) / hopMs), alpha > 0.02 ? { tone: "accent", alpha } : null);
  }

  for (const c of state.cells) {
    const local = t - reach(state, c.glyph, c.dist, startMs, stepMs);
    let px: Pixel;
    if (local < 0) px = c.task ? { tone: "accent", alpha: 0.45 } : { tone: "ink", alpha: blueprint };
    else if (c.task && local < taskMs) px = GLINT;
    else if (local < frontMs) px = ACCENT;
    else if (local < frontMs + trailMs) px = HALF;
    else px = INK;
    setPixel(frame, c.x, c.y, px);
  }
  return frame;
}

type Run = { start: number; from: number; to: number; step: number };

/** Run `i` of the LIVE schedule. Seeded per index, so any moment can be sampled. */
function run(state: TraverseState, i: number): Run {
  const rand = mulberry32((state.seed ^ Math.imul(i + 1, 0x9e3779b1)) >>> 0);
  const every = state.options.runEveryMs;
  const start = i * every + Math.floor(rand() * every * 0.4);
  if (rand() < 0.25) return { start, from: 0, to: state.glyphs - 1, step: state.options.stepMs * state.options.sprint };
  const from = Math.floor(rand() * state.glyphs);
  const to = Math.min(state.glyphs - 1, from + Math.floor(rand() * 3));
  return { start, from, to, step: state.options.stepMs };
}

function live(state: TraverseState, tLive: number): Frame {
  const frame = settled(state);
  const { frontMs, taskMs, hopMs, runEveryMs } = state.options;
  const i = Math.floor(tLive / runEveryMs);
  for (const k of [i - 2, i - 1, i]) {
    if (k < 0) continue;
    const r = run(state, k);
    if (tLive < r.start) continue;
    for (let g = r.from; g < r.to; g += 1) {
      const leave = reach(state, g, state.exitDist[g]!, r.start, r.step, r.from);
      if (tLive >= leave && tLive < leave + hopMs) paintHop(state, frame, g, (tLive - leave) / hopMs, null);
    }
    for (const c of state.cells) {
      if (c.glyph < r.from || c.glyph > r.to) continue;
      const local = tLive - reach(state, c.glyph, c.dist, r.start, r.step, r.from);
      if (local < 0) continue;
      if (c.task && local < taskMs) setPixel(frame, c.x, c.y, GLINT);
      else if (local < frontMs) setPixel(frame, c.x, c.y, ACCENT);
    }
  }
  return frame;
}
