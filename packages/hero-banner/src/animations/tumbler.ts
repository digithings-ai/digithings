import { emptyFrame, litCells, mulberry32, setPixel } from "../layout";
import type { Animation, Frame, Layout, Pixel } from "../types";

/**
 * TUMBLER (digikey). Every pixel column is a pin stack in a pin-tumbler lock.
 * LOADING: the columns start dim and out of line, each pushed up or down by a
 * seeded few pixels. A key slides in from the left along the shear line; as
 * its tip passes a column, that pin drops into line (accent), then clicks
 * (a `glint` pixel) and sets as ink. When the key is all the way in, it turns:
 * a `glint` band rolls down the word, top to bottom, and the key is gone.
 * LIVE: the word stays put. Now and then someone tries a letter: its pins
 * jiggle out of line and snap back with an accent click. One event in four is
 * a full turn of the key, the same rolling band as the end of LOADING.
 */

export type TumblerOptions = {
  /** ms for the key tip to cross the word. */
  keyMs: number;
  /** ms for a pin to drop into line once the tip has passed it. */
  settleMs: number;
  /** ms a set pin shows its click before it turns ink. */
  clickMs: number;
  /** Pause between the key landing and the turn. */
  holdMs: number;
  /** ms for the turn band to roll down the word. */
  turnMs: number;
  /** Largest pin offset, in pixels. Every pin is off by 1..maxOffset. */
  maxOffset: number;
  /** Strength of a locked (not yet set) pin. */
  locked: number;
  /** LIVE: ms between events. */
  eventEveryMs: number;
  /** LIVE: ms a picked letter stays out of line. */
  pickMs: number;
};

export type TumblerState = {
  width: number;
  height: number;
  /** Lit rows per column, so a pin can be drawn shifted as a whole. */
  columns: number[][];
  /** Glyph index per column, -1 in the gaps. */
  glyphOf: Int16Array;
  /** Signed offset of each pin before the key sets it. */
  offset: Int8Array;
  glyphs: number;
  /** Row the key blade runs along. */
  shear: number;
  seed: number;
  options: TumblerOptions;
  turnStartMs: number;
  ms: number;
};

const ACCENT: Pixel = { tone: "accent", alpha: 1 };
const GLINT: Pixel = { tone: "glint", alpha: 1 };
const INK: Pixel = { tone: "ink", alpha: 1 };

export function tumblerAnimation(options: TumblerOptions): Animation<TumblerState> {
  return {
    kind: "tumbler",
    liveTickMs: 50,
    prepare(layout: Layout, def) {
      const rand = mulberry32(def.seed);
      const columns: number[][] = Array.from({ length: layout.width }, () => []);
      const glyphOf = new Int16Array(layout.width).fill(-1);
      for (const cell of litCells(layout)) {
        columns[cell.x]!.push(cell.y);
        glyphOf[cell.x] = cell.glyph;
      }
      const offset = new Int8Array(layout.width);
      for (let x = 0; x < layout.width; x += 1) {
        const size = 1 + Math.floor(rand() * options.maxOffset);
        offset[x] = rand() < 0.5 ? -size : size;
      }
      const turnStartMs = options.keyMs + options.settleMs + options.clickMs + options.holdMs;
      return {
        width: layout.width,
        height: layout.height,
        columns,
        glyphOf,
        offset,
        glyphs: layout.starts.length,
        shear: Math.floor(layout.height / 2),
        seed: def.seed,
        options,
        turnStartMs,
        ms: turnStartMs + options.turnMs,
      };
    },
    loadingMs: (state) => state.ms,
    loading,
    live,
    still: settled,
  };
}

/** Key tip x at `t`: eases out, as a key slows when the last pins resist. */
function keyTip(state: TumblerState, t: number): number {
  const p = Math.min(1, Math.max(0, t / state.options.keyMs));
  return (1 - (1 - p) ** 2) * state.width;
}

/** When the tip reaches column `x` (inverse of keyTip). */
function tipReaches(state: TumblerState, x: number): number {
  const p = Math.min(1, (x + 0.5) / state.width);
  return (1 - Math.sqrt(1 - p)) * state.options.keyMs;
}

function paintColumn(state: TumblerState, frame: Frame, x: number, shift: number, pixel: Pixel | null): void {
  for (const y of state.columns[x]!) setPixel(frame, x, y + shift, pixel);
}

/** Paint the turn band: rows above it are ink, the band row is glint. */
function paintTurn(state: TumblerState, frame: Frame, p: number): void {
  const band = Math.floor(p * (state.height + 1)) - 1;
  for (let x = 0; x < state.width; x += 1) {
    for (const y of state.columns[x]!) if (y === band || y === band - 1) setPixel(frame, x, y, y === band ? GLINT : ACCENT);
  }
}

function loading(state: TumblerState, t: number): Frame {
  const frame = emptyFrame(state.width, state.height);
  const { settleMs, clickMs, locked, turnMs } = state.options;
  const tip = keyTip(state, t);
  const turning = t >= state.turnStartMs;

  for (let x = 0; x < state.width; x += 1) {
    if (state.columns[x]!.length === 0) continue;
    const local = t - tipReaches(state, x);
    if (local < 0) {
      // Locked: out of line and dim. A one-pixel rattle as the key nears.
      const near = x - tip < 4 && Math.floor(t / 70 + x) % 2 === 0 ? Math.sign(state.offset[x]!) : 0;
      paintColumn(state, frame, x, state.offset[x]! - near, { tone: "ink", alpha: locked });
    } else if (local < settleMs) {
      const p = local / settleMs;
      paintColumn(state, frame, x, Math.round(state.offset[x]! * (1 - p) ** 2), ACCENT);
    } else if (local < settleMs + clickMs) {
      paintColumn(state, frame, x, 0, GLINT);
    } else {
      paintColumn(state, frame, x, 0, INK);
    }
  }

  if (!turning) {
    // The key blade along the shear line, on empty pixels only: the bow stays
    // off-canvas left, the tip is the brightest pixel.
    const head = Math.min(state.width - 1, Math.floor(tip));
    for (let x = 0; x <= head; x += 1) {
      if (state.columns[x]!.includes(state.shear)) continue;
      setPixel(frame, x, state.shear, x === head ? ACCENT : { tone: "accent", alpha: 0.4 });
      // Bitting: a tooth every third pixel on the row above.
      if (x % 3 === 0 && !state.columns[x]!.includes(state.shear - 1)) {
        setPixel(frame, x, state.shear - 1, { tone: "accent", alpha: 0.22 });
      }
    }
  } else {
    paintTurn(state, frame, Math.min(1, (t - state.turnStartMs) / turnMs));
  }
  return frame;
}

function settled(state: TumblerState): Frame {
  const frame = emptyFrame(state.width, state.height);
  for (let x = 0; x < state.width; x += 1) paintColumn(state, frame, x, 0, INK);
  return frame;
}

type LiveEvent = { start: number; turn: boolean; glyph: number };

/** Event `i` of the LIVE schedule. Seeded per index, so any moment can be sampled. */
function event(state: TumblerState, i: number): LiveEvent {
  const rand = mulberry32((state.seed ^ Math.imul(i + 1, 0x9e3779b1)) >>> 0);
  const every = state.options.eventEveryMs;
  const start = i * every + Math.floor(rand() * every * 0.5);
  const turn = rand() < 0.25;
  return { start, turn, glyph: Math.floor(rand() * state.glyphs) };
}

function live(state: TumblerState, tLive: number): Frame {
  const frame = settled(state);
  const { eventEveryMs, pickMs, clickMs, turnMs } = state.options;
  const i = Math.floor(tLive / eventEveryMs);
  for (const k of [i - 1, i]) {
    if (k < 0) continue;
    const e = event(state, k);
    const age = tLive - e.start;
    if (age < 0) continue;
    if (e.turn) {
      if (age < turnMs) paintTurn(state, frame, age / turnMs);
      continue;
    }
    if (age >= pickMs + clickMs) continue;
    for (let x = 0; x < state.width; x += 1) {
      if (state.glyphOf[x] !== e.glyph) continue;
      paintColumn(state, frame, x, 0, null);
      if (age < pickMs) {
        // The pick lifts each pin by one pixel, out of phase with its neighbour.
        const up = Math.floor(age / 90 + x) % 2 === 0 ? -1 : 1;
        paintColumn(state, frame, x, up * Math.sign(state.offset[x]!), { tone: "ink", alpha: 0.6 });
      } else {
        paintColumn(state, frame, x, 0, ACCENT);
      }
    }
  }
  return frame;
}
