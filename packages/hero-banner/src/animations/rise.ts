import { emptyFrame, litCells, mulberry32, setPixel } from "../layout";
import type { Animation, Frame, Layout } from "../types";

/**
 * RISE (digiquant). LOADING: cells grow up from the baseline, column by column
 * left to right, like bars building the word, in the up and down tones, then
 * settle to ink; strays blink once. LIVE: a few cells glint in the accent.
 * Port of apps/digiquant-web/app/_chrome/QuantWordmark.tsx (#4986) and its
 * dq-rise / dq-stray / dq-glint keyframes: same seed, same draw order.
 */

export type RiseOptions = {
  /** Wordmark column timing, shared with the digiquant hero chart sweep. */
  startMs: number;
  columnMs: number;
  glintChance: number;
  strays: number;
  glintDuty: number;
  /** Share of the rise spent in the up/down tone before it turns to ink. */
  toneUntil: number;
};

type RiseCell = {
  x: number;
  y: number;
  delay: number;
  dur: number;
  tone: "up" | "down";
  glint: { period: number; offset: number } | null;
};

type Stray = { x: number; y: number; delay: number; dur: number; tone: "up" | "down" };

export type RiseState = { width: number; height: number; cells: RiseCell[]; strays: Stray[]; options: RiseOptions; ms: number };

/** cubic-bezier(0.2, 0.7, 0.2, 1), solved for y at time x. */
export function riseEase(x: number): number {
  if (x <= 0) return 0;
  if (x >= 1) return 1;
  const p1x = 0.2, p1y = 0.7, p2x = 0.2, p2y = 1;
  const bx = (s: number) => 3 * (1 - s) * (1 - s) * s * p1x + 3 * (1 - s) * s * s * p2x + s * s * s;
  const by = (s: number) => 3 * (1 - s) * (1 - s) * s * p1y + 3 * (1 - s) * s * s * p2y + s * s * s;
  let lo = 0, hi = 1;
  for (let i = 0; i < 24; i += 1) {
    const mid = (lo + hi) / 2;
    if (bx(mid) < x) lo = mid;
    else hi = mid;
  }
  return by((lo + hi) / 2);
}

/** The rise must show both sides of the pair, not a run of one tone. */
function mixDirections(cells: { tone: "up" | "down" }[]): void {
  if (cells.length < 2) return;
  if (!cells.some((c) => c.tone === "up")) cells[0]!.tone = "up";
  if (!cells.some((c) => c.tone === "down")) cells[1]!.tone = "down";
}

export function riseAnimation(options: RiseOptions): Animation<RiseState> {
  const columnDelay = (col: number) => options.startMs + col * options.columnMs;
  return {
    kind: "rise",
    liveTickMs: 100,
    prepare(layout: Layout, def) {
      const rand = mulberry32(def.seed);
      const used = new Set<string>();
      const cells: RiseCell[] = [];
      for (const cell of litCells(layout)) {
        used.add(`${cell.x},${cell.y}`);
        const glint = rand() < options.glintChance;
        const delay = columnDelay(cell.x) + (layout.height - 1 - cell.y) * 9 + Math.floor(rand() * 140);
        const dur = 260 + Math.floor(rand() * 220);
        const g = glint ? { period: 7000 + Math.floor(rand() * 8000), offset: 3500 + Math.floor(rand() * 6000) } : null;
        cells.push({ x: cell.x, y: cell.y, delay, dur, tone: rand() < 0.5 ? "up" : "down", glint: g });
      }
      mixDirections(cells);
      const strays: Stray[] = [];
      while (strays.length < options.strays) {
        const x = Math.floor(rand() * layout.width);
        const y = Math.floor(rand() * layout.height);
        const key = `${x},${y}`;
        if (used.has(key)) continue;
        used.add(key);
        const dur = 60 + Math.floor(rand() * 140);
        const delay = Math.floor(rand() * 1400);
        strays.push({ x, y, delay, dur, tone: rand() < 0.5 ? "up" : "down" });
      }
      mixDirections(strays);
      const ms = Math.max(0, ...cells.map((c) => c.delay + c.dur), ...strays.map((s) => s.delay + s.dur));
      return { width: layout.width, height: layout.height, cells, strays, options, ms };
    },
    loadingMs: (state) => state.ms,
    loading(state, t) {
      const frame = emptyFrame(state.width, state.height);
      for (const cell of state.cells) {
        const p = (t - cell.delay) / cell.dur;
        if (p <= 0) continue;
        // A terminal cell cannot scale on Y, so the rise reads as opacity.
        const alpha = riseEase(p);
        setPixel(frame, cell.x, cell.y, { tone: p < state.options.toneUntil ? cell.tone : "ink", alpha });
      }
      for (const stray of state.strays) {
        if (t >= stray.delay && t < stray.delay + stray.dur) {
          setPixel(frame, stray.x, stray.y, { tone: stray.tone, alpha: 0.25 });
        }
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

function settled(state: RiseState): Frame {
  const frame = emptyFrame(state.width, state.height);
  for (const cell of state.cells) setPixel(frame, cell.x, cell.y, { tone: "ink", alpha: 1 });
  return frame;
}

function paintGlints(frame: Frame, state: RiseState, t: number): void {
  for (const cell of state.cells) {
    if (!cell.glint || t < cell.glint.offset) continue;
    if ((t - cell.glint.offset) % cell.glint.period < cell.glint.period * state.options.glintDuty) {
      setPixel(frame, cell.x, cell.y, { tone: "accent", alpha: 1 });
    }
  }
}
