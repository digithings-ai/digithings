import { emptyFrame, litCells, mulberry32, setPixel } from "../layout";
import type { Animation, Frame, Layout } from "../types";

/**
 * BUILD (digithings). LOADING: each cell flickers through three opacity steps
 * and lands on its own final step; strays blink once at 0.25. LIVE: a few cells
 * glint in the accent on long, uneven periods.
 * Port of apps/digithings-web/components/landing/PixelWordmark.tsx and its
 * pixel-build / pixel-stray / pixel-glint keyframes: same seed, same draw order.
 */

export type BuildOptions = {
  /** Opacity steps a cell can land on. */
  steps: readonly number[];
  glints: number;
  strays: number;
  /** Stray columns are drawn from [0, strayWidth). Defaults to the layout width. */
  strayWidth?: number;
  /** Share of the glint period the accent shows. */
  glintDuty: number;
};

type BuildCell = {
  x: number;
  y: number;
  d: number;
  t: number;
  a: number;
  b: number;
  c: number;
  f: number;
  glint: { g: number; gp: number } | null;
};

type Stray = { x: number; y: number; d: number; t: number };

export type BuildState = { width: number; height: number; cells: BuildCell[]; strays: Stray[]; duty: number; ms: number };

export function buildAnimation(options: BuildOptions): Animation<BuildState> {
  return {
    kind: "build",
    liveTickMs: 100,
    prepare(layout: Layout, def) {
      const rand = mulberry32(def.seed);
      const pick = () => options.steps[Math.floor(rand() * options.steps.length)] ?? 1;
      const used = new Set<string>();
      const lit = litCells(layout);
      for (const cell of lit) used.add(`${cell.x},${cell.y}`);
      const glint = new Set<number>();
      while (glint.size < Math.min(options.glints, lit.length)) glint.add(Math.floor(rand() * lit.length));
      const cells: BuildCell[] = lit.map((cell, index) => {
        const isGlint = glint.has(index);
        const d = (rand() * 692 + 8) | 0;
        const t = (rand() * 380 + 240) | 0;
        const a = pick();
        const b = pick();
        const c = pick();
        const f = pick();
        const g = isGlint ? { g: (rand() * 6500 + 2500) | 0, gp: (rand() * 8000 + 7000) | 0 } : null;
        return { x: cell.x, y: cell.y, d, t, a, b, c, f, glint: g };
      });
      const strays: Stray[] = [];
      const strayWidth = options.strayWidth ?? layout.width;
      while (strays.length < options.strays) {
        const x = Math.floor(rand() * strayWidth);
        const y = Math.floor(rand() * layout.height);
        const key = `${x},${y}`;
        if (used.has(key)) continue;
        used.add(key);
        strays.push({ x, y, d: (rand() * 1100) | 0, t: (rand() * 140 + 60) | 0 });
      }
      const ms = Math.max(0, ...cells.map((c) => c.d + c.t), ...strays.map((s) => s.d + s.t));
      return { width: layout.width, height: layout.height, cells, strays, duty: options.glintDuty, ms };
    },
    loadingMs: (state) => state.ms,
    loading(state, t) {
      const frame = emptyFrame(state.width, state.height);
      for (const cell of state.cells) {
        const p = (t - cell.d) / cell.t;
        if (p < 0) continue;
        const alpha = p < 1 / 3 ? cell.a : p < 2 / 3 ? cell.b : p < 1 ? cell.c : cell.f;
        setPixel(frame, cell.x, cell.y, { tone: "ink", alpha });
      }
      for (const stray of state.strays) {
        if (t >= stray.d && t < stray.d + stray.t) setPixel(frame, stray.x, stray.y, { tone: "ink", alpha: 0.25 });
      }
      paintGlints(frame, state, t);
      return frame;
    },
    live(state, _tLive, tMount) {
      const frame = settled(state);
      paintGlints(frame, state, tMount);
      return frame;
    },
    still: settled,
  };
}

function settled(state: BuildState): Frame {
  const frame = emptyFrame(state.width, state.height);
  for (const cell of state.cells) setPixel(frame, cell.x, cell.y, { tone: "ink", alpha: cell.f });
  return frame;
}

/** `pixel-glint var(--gp) step-end var(--g) infinite`: accent for the first
 *  `duty` of each period once the delay has passed. */
function paintGlints(frame: Frame, state: BuildState, t: number): void {
  for (const cell of state.cells) {
    if (!cell.glint || t < cell.glint.g) continue;
    if ((t - cell.glint.g) % cell.glint.gp < cell.glint.gp * state.duty) {
      setPixel(frame, cell.x, cell.y, { tone: "accent", alpha: 1 });
    }
  }
}
