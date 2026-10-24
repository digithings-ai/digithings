import { emptyFrame, litCells, setPixel } from "../layout";
import type { Animation, Frame, Layout } from "../types";

/**
 * EQUALIZER (digivoice). Every pixel of the word is lit in the rest tone; a
 * level rises and falls per column and brightens pixels from the bottom up.
 * LOADING: the level swells from silence to full over `buildMs`. LIVE: the
 * level keeps moving. The settled mark is the frame at `buildMs`, the moment
 * digivoice/tui/src/hero.js draws by default.
 * Port of digivoice/tui/src/hero.js (#4965 / #4959): same level function.
 */

export type EqualizerOptions = { buildMs: number };

type Column = { x: number; ys: number[] };

export type EqualizerState = { width: number; height: number; columns: Column[]; buildMs: number };

/** 0..1 level of `column` at `tMs`. Two sines, slow and fast. */
export function levelFrac(column: number, tMs: number): number {
  const t = Math.max(0, Number.isFinite(tMs) ? tMs : 0);
  const slow = Math.sin(t / 380 + column * 0.73);
  const fast = Math.sin(t / 170 + column * 1.37);
  return (slow * 0.65 + fast * 0.35 + 1) / 2;
}

function draw(state: EqualizerState, tMs: number, envelope: number): Frame {
  const frame = emptyFrame(state.width, state.height);
  for (const column of state.columns) {
    const reach = levelFrac(column.x, tMs) * column.ys.length * envelope;
    column.ys.forEach((y, index) => {
      setPixel(frame, column.x, y, { tone: index < reach ? "lit" : "rest", alpha: 1 });
    });
  }
  return frame;
}

export function equalizerAnimation(options: EqualizerOptions): Animation<EqualizerState> {
  return {
    kind: "equalizer",
    liveTickMs: 60,
    prepare(layout: Layout) {
      const byX = new Map<number, number[]>();
      for (const cell of litCells(layout)) {
        const ys = byX.get(cell.x) ?? [];
        ys.push(cell.y);
        byX.set(cell.x, ys);
      }
      const columns = [...byX.entries()]
        .sort((a, b) => a[0] - b[0])
        .map(([x, ys]) => ({ x, ys: ys.sort((a, b) => b - a) }));
      return { width: layout.width, height: layout.height, columns, buildMs: options.buildMs };
    },
    loadingMs: (state) => state.buildMs,
    loading: (state, t) => draw(state, t, Math.min(1, Math.max(0, t / state.buildMs))),
    live: (state, _tLive, tMount) => draw(state, tMount, 1),
    still: (state) => draw(state, state.buildMs, 1),
  };
}
