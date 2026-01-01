import { emptyFrame, litCells, mulberry32, setPixel } from "../layout";
import type { Animation, Frame, Layout, Pixel } from "../types";

/**
 * VAULT (digivault). The word is kept behind a vault door, and the door opens.
 * LOADING: a closed door (a dim `accent` plate) covers the word. A seam runs down
 * the middle and two locking bolts cross it. On the left leaf a combination dial
 * turns: right, left, right, each stop a `glint` click. The bolts then slide
 * back into the right leaf, the two leaves part from the seam with `glint` edges,
 * and the word inside shows in `accent`. Then the lights come on: a seeded
 * dissolve turns the word to ink.
 * LIVE: a watch loop. Every so often a scan line runs down the word (vertical, a
 * `glint` row with a faint `accent` line across the frame), or the bolts shoot
 * across the gaps from the seam, hold and draw back (a relock check).
 */

export type VaultOptions = {
  /** LOADING: ms of each of the three dial turns (turn and click). */
  turnMs: number;
  /** ms the bolts take to slide back. */
  boltMs: number;
  /** ms the leaves take to part. */
  openMs: number;
  /** ms of the dissolve from `accent` to ink. */
  settleMs: number;
  /** LIVE: ms between watch events. */
  everyMs: number;
  /** LIVE: ms of one scan from top to bottom. */
  scanMs: number;
};

export type VaultState = {
  width: number;
  height: number;
  layout: Layout;
  cells: { x: number; y: number }[];
  /** Per lit cell, the share of the dissolve at which it turns to ink. */
  order: number[];
  seam: number;
  /** Dial centre and radius, on the left leaf. */
  dial: { cx: number; cy: number; r: number };
  /** Rows the bolts run on. */
  boltRows: number[];
  boltLen: number;
  boltAt: number;
  openAt: number;
  settleAt: number;
  ms: number;
  seed: number;
  options: VaultOptions;
};

/** Dial stops, as turns from 12 o'clock: right, left, right. */
const STOPS = [0.62, -0.18, 0.4];

const PLATE: Pixel = { tone: "accent", alpha: 0.22 };
const RING: Pixel = { tone: "accent", alpha: 0.6 };
const BOLT: Pixel = { tone: "accent", alpha: 0.9 };
const GLINT: Pixel = { tone: "glint", alpha: 1 };
const SOURCE: Pixel = { tone: "accent", alpha: 0.9 };
const INK: Pixel = { tone: "ink", alpha: 1 };

const ease = (p: number) => (p < 0.5 ? 2 * p * p : 1 - (-2 * p + 2) ** 2 / 2);
const clamp01 = (p: number) => Math.max(0, Math.min(1, p));

export function vaultAnimation(options: VaultOptions): Animation<VaultState> {
  return {
    kind: "vault",
    liveTickMs: 40,
    prepare(layout: Layout, def) {
      const { width, height } = layout;
      const rand = mulberry32(def.seed);
      const cells = litCells(layout).map(({ x, y }) => ({ x, y }));
      const order = cells.map(() => rand());
      const seam = Math.floor(width / 2);
      const r = Math.max(2, Math.floor(height / 2) - 1);
      const dial = { cx: Math.round(width / 4), cy: (height - 1) / 2, r };
      const boltRows = [Math.round(height * 0.25), Math.round(height * 0.75) - 1];
      const boltLen = Math.max(3, Math.round(width / 10));
      const boltAt = STOPS.length * options.turnMs;
      const openAt = boltAt + options.boltMs;
      const settleAt = openAt + options.openMs;
      const ms = settleAt + options.settleMs;
      return { width, height, layout, cells, order, seam, dial, boltRows, boltLen, boltAt, openAt, settleAt, ms, seed: def.seed, options };
    },
    loadingMs: (state) => state.ms,
    loading,
    live,
    still: settled,
  };
}

/** Dial angle (turns) and whether a stop has just clicked, `t` ms into LOADING. */
export function dialAt(state: VaultState, t: number): { turn: number; click: boolean } {
  const { turnMs } = state.options;
  const i = Math.min(STOPS.length - 1, Math.floor(t / turnMs));
  const from = i === 0 ? 0 : STOPS[i - 1];
  const into = t - i * turnMs;
  const p = clamp01(into / (turnMs * 0.8));
  return { turn: from + (STOPS[i] - from) * ease(p), click: p >= 1 && t < STOPS.length * turnMs };
}

/** The closed door in leaf space: plate, dial, and bolts shifted right by `shift`. */
function door(state: VaultState, x: number, y: number, turn: number, click: boolean, shift: number): Pixel | null {
  const { seam, dial, boltRows, boltLen } = state;
  if (x === seam) return null;
  if (boltRows.includes(y) && x >= seam - boltLen + shift && x <= seam + boltLen + shift) return BOLT;
  const dx = x - dial.cx;
  const dy = y - dial.cy;
  const d = Math.hypot(dx, dy);
  if (d >= 1 && d < dial.r + 0.6) {
    // The hand: a spoke cut from the hub to the ring at the dial angle (0 = 12
    // o'clock, clockwise), filled with `glint` on each click. Cut, not tinted,
    // so the turn shows in the shape and not only the colour: a terminal cell
    // draws lit-or-empty, never tone, and a spoke spans enough columns to
    // survive the terminal's narrower gaps.
    const a = Math.atan2(dx, -dy) / (2 * Math.PI);
    const off = Math.abs(((a - turn) % 1 + 1.5) % 1 - 0.5);
    if (off < 0.5 / (2 * Math.PI * d) + 0.02) return click ? GLINT : null;
  }
  if (Math.abs(d - dial.r) < 0.6) return click ? BOLT : RING;
  if (d < 1) return RING;
  return PLATE;
}

function loading(state: VaultState, t: number): Frame {
  const frame = emptyFrame(state.width, state.height);
  if (t >= state.settleAt) {
    const p = clamp01((t - state.settleAt) / state.options.settleMs);
    state.cells.forEach((c, i) => setPixel(frame, c.x, c.y, state.order[i] < p ? INK : SOURCE));
    return frame;
  }
  const { turn, click } = dialAt(state, Math.min(t, state.boltAt - 1));
  const shift = Math.round(state.boltLen * clamp01((t - state.boltAt) / state.options.boltMs));
  // The leaves part from the seam: left leaf slides left, right leaf right.
  const d = t < state.openAt ? 0 : Math.round(ease(clamp01((t - state.openAt) / state.options.openMs)) * (state.seam + 1));
  const lit = new Set(state.cells.map((c) => c.y * state.width + c.x));
  for (let y = 0; y < state.height; y += 1) {
    for (let x = 0; x < state.width; x += 1) {
      let px: Pixel | null;
      if (d === 0) px = door(state, x, y, turn, click, shift);
      else if (x < state.seam - d) px = door(state, x + d, y, turn, false, shift);
      else if (x > state.seam + d) px = door(state, x - d, y, turn, false, shift);
      else if (x === state.seam - d || x === state.seam + d) px = GLINT;
      else px = lit.has(y * state.width + x) ? SOURCE : null;
      setPixel(frame, x, y, px);
    }
  }
  return frame;
}

function settled(state: VaultState): Frame {
  const frame = emptyFrame(state.width, state.height);
  for (const c of state.cells) setPixel(frame, c.x, c.y, INK);
  return frame;
}

export type WatchEvent = { at: number; kind: "scan" | "relock" };

/** LIVE event `i`, seeded per index so any moment can be sampled. */
export function liveEvent(state: VaultState, i: number): WatchEvent {
  const rand = mulberry32((state.seed ^ Math.imul(i + 1, 0x9e3779b1)) >>> 0);
  const { everyMs } = state.options;
  const at = i * everyMs + Math.floor(rand() * everyMs * 0.4);
  return { at, kind: rand() < 1 / 3 ? "relock" : "scan" };
}

/** Relock: bolts grow from the seam over the gaps, hold, and draw back. */
const RELOCK = { grow: 320, hold: 420, back: 320 };

function live(state: VaultState, tLive: number): Frame {
  const frame = settled(state);
  const i = Math.floor(tLive / state.options.everyMs);
  for (const j of [i - 1, i]) {
    if (j < 0) continue;
    const ev = liveEvent(state, j);
    const dt = tLive - ev.at;
    if (dt <= 0) continue;
    if (ev.kind === "scan") {
      const p = dt / state.options.scanMs;
      if (p >= 1) continue;
      const row = Math.floor(p * (state.height + 2)) - 1;
      if (row < 0 || row >= state.height) continue;
      for (let x = 0; x < state.width; x += 1) {
        setPixel(frame, x, row, frame.pixels[row * state.width + x] ? GLINT : PLATE);
      }
      continue;
    }
    const end = RELOCK.grow + RELOCK.hold + RELOCK.back;
    if (dt >= end) continue;
    const p = dt < RELOCK.grow ? dt / RELOCK.grow : dt < RELOCK.grow + RELOCK.hold ? 1 : (end - dt) / RELOCK.back;
    const reach = Math.round(ease(p) * (state.seam + 1));
    for (const y of state.boltRows) {
      for (let x = state.seam - reach; x <= state.seam + reach; x += 1) {
        if (!frame.pixels[y * state.width + x]) setPixel(frame, x, y, { tone: "accent", alpha: 0.5 });
      }
    }
  }
  return frame;
}
