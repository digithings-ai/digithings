import { emptyFrame, litCells, mulberry32, setPixel } from "../layout";
import type { Animation, Frame, Glyph, Layout, Pixel, PixelFont } from "../types";

/**
 * CLAW (digiclaw). An arcade claw machine picks the word out of a pile.
 * The font carries `HEADROOM` blank rows over each glyph; that is the claw's
 * gantry. LOADING: the glyphs lie sunk in a pile at the bottom (dim `accent`,
 * seeded depths). A claw (`accent`) hangs from a faint rail, travels to each
 * slot, drops, closes on the glyph, lifts it into place and lets go; the
 * glyph flashes `glint` and settles to `ink`. The claw starts slow and gets
 * quicker. One seeded grab slips: the glyph falls back to the pile and the
 * claw tries again. Then the claw leaves and the rail fades.
 * LIVE: every so often the claw drops on one glyph, lifts it into the
 * headroom, holds it and sets it back down. One event in three it slips: the
 * glyph drops back with a small bounce.
 */

export const HEADROOM = 4;

/** `font` with `rows` blank rows on top of every glyph (rows stays even). */
export function withHeadroom(font: PixelFont, rows = HEADROOM): PixelFont {
  const blank = ".".repeat(font.cols);
  const glyphs: Record<string, Glyph> = {};
  for (const [ch, g] of Object.entries(font.glyphs)) glyphs[ch] = [...Array(rows).fill(blank), ...g];
  return { cols: font.cols, rows: font.rows + rows, glyphs };
}

export type ClawOptions = {
  /** LOADING: ms the claw takes to enter from the left. */
  enterMs: number;
  /** ms to travel to the next slot (rising back to the rail). */
  travelMs: number;
  /** ms to drop onto a glyph. */
  dropMs: number;
  /** ms the claw takes to close. */
  gripMs: number;
  /** ms to lift a glyph into place. */
  liftMs: number;
  /** ms the claw holds before it travels on. */
  releaseMs: number;
  /** ms a released glyph shows `glint`. */
  flashMs: number;
  /** Pace of the first grab; later grabs speed up to `paceMin`. */
  paceStart: number;
  paceMin: number;
  /** ms for the claw to leave and the rail to fade. */
  exitMs: number;
  /** LIVE: ms between claw events. */
  everyMs: number;
};

/** A value that moves from `a` to `b` over [t0, t1]. */
type Seg = { t0: number; t1: number; a: number; b: number; ease: (p: number) => number };

/** Piecewise track: holds `init` until the first segment, then the last value reached. */
export type Track = { init: number; segs: Seg[] };

export type Script = {
  /** Claw centre column and head row (head = the 3-wide bar; prongs hang 2 rows under it). */
  cx: Track;
  head: Track;
  /** Claw open/closed toggles, in time order. Starts open. */
  closed: { t: number; closed: boolean }[];
  /** Claw shown over [from, to). */
  from: number;
  to: number;
  /** Per glyph slot: rows below home (positive: sunk; negative: lifted into headroom). */
  offset: Track[];
  /** Per glyph slot: when it stops being "pile" (gripped), and when it settles (released). */
  gripped: (number | null)[];
  placed: (number | null)[];
  /** Slot that drops back without a grip after a slip, from `t`: tone back to pile. */
  dropped: { slot: number; t: number }[];
  /** How an ungripped glyph looks: the pile (LOADING) or the settled ink (LIVE). */
  rest: Pixel;
};

export type ClawState = {
  width: number;
  height: number;
  layout: Layout;
  cells: { x: number; y: number }[][];
  centers: number[];
  sinks: number[];
  /** Slot whose first LOADING grab slips. */
  slipSlot: number;
  script: Script;
  seed: number;
  options: ClawOptions;
  ms: number;
};

const easeOut = (p: number) => 1 - (1 - p) * (1 - p);
const easeIn = (p: number) => p * p;
const easeInOut = (p: number) => (p < 0.5 ? 2 * p * p : 1 - 2 * (1 - p) * (1 - p));

export function valueAt(track: Track, t: number): number {
  let v = track.init;
  for (const s of track.segs) {
    if (t < s.t0) break;
    if (t >= s.t1) {
      v = s.b;
      continue;
    }
    return s.a + (s.b - s.a) * s.ease((t - s.t0) / (s.t1 - s.t0));
  }
  return v;
}

/** The head row at which the prong tips sit one row into a glyph at `offset`. */
const gripHead = (offset: number) => HEADROOM - 1 + offset;
const RAIL_HEAD = 1;

/** Builds a claw script: moves are appended in time order. */
class Director {
  t = 0;
  cx: Track;
  head: Track;
  closed: Script["closed"] = [];
  offset: Track[];
  gripped: (number | null)[];
  placed: (number | null)[];
  dropped: Script["dropped"] = [];
  constructor(cx: number, head: number, offsets: number[]) {
    this.cx = { init: cx, segs: [] };
    this.head = { init: head, segs: [] };
    this.offset = offsets.map((o) => ({ init: o, segs: [] }));
    this.gripped = offsets.map(() => null);
    this.placed = offsets.map(() => null);
  }
  private last(track: Track) {
    return track.segs.at(-1)?.b ?? track.init;
  }
  move(ms: number, to: { cx?: number; head?: number }, ease = easeInOut) {
    const t0 = this.t;
    const t1 = t0 + Math.max(1, Math.round(ms));
    if (to.cx != null) this.cx.segs.push({ t0, t1, a: this.last(this.cx), b: to.cx, ease });
    if (to.head != null) this.head.segs.push({ t0, t1, a: this.last(this.head), b: to.head, ease });
    return { t0, t1 };
  }
  shift(slot: number, t0: number, t1: number, to: number, ease: (p: number) => number) {
    const tr = this.offset[slot];
    tr.segs.push({ t0, t1, a: this.last(tr), b: to, ease });
  }
  grip(closed: boolean) {
    this.closed.push({ t: this.t, closed });
  }
  wait(ms: number) {
    this.t += Math.round(ms);
  }
  /** Run `move`, then advance time to its end. */
  go(ms: number, to: { cx?: number; head?: number }, ease = easeInOut) {
    const span = this.move(ms, to, ease);
    this.t = span.t1;
    return span;
  }
  script(from: number, to: number, rest: Pixel): Script {
    const { cx, head, closed, offset, gripped, placed, dropped } = this;
    return { cx, head, closed, from, to, offset, gripped, placed, dropped, rest };
  }
}

export function clawAnimation(options: ClawOptions): Animation<ClawState> {
  return {
    kind: "claw",
    liveTickMs: 40,
    prepare(layout: Layout, def) {
      const { width, height } = layout;
      const rand = mulberry32(def.seed);
      const n = layout.text.length;
      const cells: { x: number; y: number }[][] = Array.from({ length: n }, () => []);
      for (const c of litCells(layout)) cells[c.glyph].push({ x: c.x, y: c.y });
      const half = Math.floor(layout.font.cols / 2);
      const centers = layout.starts.map((s) => s + half);
      // Sunk depths: the glyph tops sit in the bottom few rows, uneven like a pile.
      const sinks = centers.map(() => 5 + Math.floor(rand() * 3));
      const slipSlot = n > 3 ? 2 + Math.floor(rand() * (n - 3)) : -1;

      const o = options;
      const d = new Director(-half - 2, RAIL_HEAD, sinks);
      d.go(o.enterMs, { cx: centers[0] }, easeOut);
      for (let slot = 0; slot < n; slot += 1) {
        const pace = Math.max(o.paceMin, o.paceStart - (o.paceStart - o.paceMin) * (slot / Math.max(1, n - 2)));
        if (slot > 0) d.go(o.travelMs * pace, { cx: centers[slot], head: RAIL_HEAD });
        const attempts = slot === slipSlot ? 2 : 1;
        for (let a = 0; a < attempts; a += 1) {
          const sink = sinks[slot];
          d.go(o.dropMs * pace, { head: gripHead(sink) }, easeIn);
          d.grip(true);
          if (d.gripped[slot] == null) d.gripped[slot] = d.t;
          d.wait(o.gripMs * pace);
          if (a < attempts - 1) {
            // The slip: halfway up the glyph falls back, the claw springs open and rises empty.
            const mid = Math.ceil(sink / 2);
            const up = d.go((o.liftMs * pace) / 2, { head: gripHead(mid) }, easeOut);
            d.shift(slot, up.t0, up.t1, mid, easeOut);
            d.grip(false);
            d.dropped.push({ slot, t: d.t });
            d.shift(slot, d.t, d.t + o.dropMs * 0.8, sink, easeIn);
            d.go(o.dropMs, { head: RAIL_HEAD }, easeOut);
            d.wait(o.releaseMs);
            continue;
          }
          const up = d.go(o.liftMs * pace, { head: gripHead(0) }, easeOut);
          d.shift(slot, up.t0, up.t1, 0, easeOut);
          d.grip(false);
          d.placed[slot] = d.t;
          d.wait(o.releaseMs * pace);
        }
      }
      d.go(o.exitMs, { cx: width + half + 2, head: RAIL_HEAD - 4 }, easeIn);
      const ms = Math.max(d.t, (d.placed.at(-1) ?? 0) + o.flashMs);
      const script = d.script(0, d.t, PILE);
      return { width, height, layout, cells, centers, sinks, slipSlot, script, seed: def.seed, options, ms };
    },
    loadingMs: (state) => state.ms,
    loading,
    live,
    still: settled,
  };
}

const PILE: Pixel = { tone: "accent", alpha: 0.35 };
const HELD: Pixel = { tone: "ink", alpha: 0.6 };
const CLAW: Pixel = { tone: "accent", alpha: 1 };
const CABLE: Pixel = { tone: "accent", alpha: 0.55 };
const GLINT: Pixel = { tone: "glint", alpha: 1 };
const INK: Pixel = { tone: "ink", alpha: 1 };

function isClosed(script: Script, t: number): boolean {
  let closed = false;
  for (const c of script.closed) {
    if (c.t > t) break;
    closed = c.closed;
  }
  return closed;
}

/** The claw: cable from the rail, a 3-wide head bar, two prongs (open: splayed;
 *  closed: tips turned in). */
export function drawClaw(frame: Frame, cx: number, head: number, closed: boolean) {
  for (let y = 0; y < head; y += 1) setPixel(frame, cx, y, CABLE);
  for (let dx = -1; dx <= 1; dx += 1) setPixel(frame, cx + dx, head, CLAW);
  setPixel(frame, cx - 2, head + 1, CLAW);
  setPixel(frame, cx + 2, head + 1, CLAW);
  const tip = closed ? 1 : 3;
  setPixel(frame, cx - tip, head + 2, CLAW);
  setPixel(frame, cx + tip, head + 2, CLAW);
}

function glyphPixel(state: ClawState, script: Script, slot: number, t: number): Pixel {
  const placed = script.placed[slot];
  if (placed != null && t >= placed) return t < placed + state.options.flashMs ? GLINT : INK;
  const drop = script.dropped.find((d) => d.slot === slot && d.t <= t);
  const regrip = script.closed.find((c) => c.closed && drop && c.t > drop.t && c.t <= t);
  const gripped = script.gripped[slot];
  if (drop && !regrip) return script.rest;
  return gripped != null && t >= gripped ? HELD : script.rest;
}

function paint(state: ClawState, script: Script, t: number, frame: Frame) {
  state.cells.forEach((cells, slot) => {
    const off = Math.round(valueAt(script.offset[slot], t));
    const px = glyphPixel(state, script, slot, t);
    for (const c of cells) setPixel(frame, c.x, c.y + off, px);
  });
  if (t >= script.from && t < script.to) {
    drawClaw(frame, Math.round(valueAt(script.cx, t)), Math.round(valueAt(script.head, t)), isClosed(script, t));
  }
}

function loading(state: ClawState, t: number): Frame {
  const frame = emptyFrame(state.width, state.height);
  // The rail: faint, fading out as the claw leaves.
  const exitAt = state.script.to - state.options.exitMs;
  const rail = t < exitAt ? 0.22 : 0.22 * Math.max(0, 1 - (t - exitAt) / state.options.exitMs);
  if (rail > 0.01) for (let x = 0; x < state.width; x += 1) setPixel(frame, x, 0, { tone: "accent", alpha: rail });
  paint(state, state.script, t, frame);
  return frame;
}

function settled(state: ClawState): Frame {
  const frame = emptyFrame(state.width, state.height);
  for (const slot of state.cells) for (const c of slot) setPixel(frame, c.x, c.y, INK);
  return frame;
}

export type ClawEvent = { at: number; kind: "pluck" | "slip"; slot: number };

/** LIVE event `i`, seeded per index so any moment can be sampled. */
export function liveEvent(state: ClawState, i: number): ClawEvent {
  const rand = mulberry32((state.seed ^ Math.imul(i + 1, 0x9e3779b1)) >>> 0);
  const { everyMs } = state.options;
  const at = i * everyMs + Math.floor(rand() * everyMs * 0.4);
  const kind = rand() < 1 / 3 ? "slip" : "pluck";
  const slot = Math.floor(rand() * state.cells.length);
  return { at, kind, slot };
}

/** The script of one LIVE event, in ms from its start. */
export function liveScript(state: ClawState, ev: ClawEvent): Script {
  const o = state.options;
  const n = state.cells.length;
  const d = new Director(state.centers[ev.slot], RAIL_HEAD - 4, Array(n).fill(0));
  d.go(o.dropMs * 1.6, { head: gripHead(0) }, easeIn);
  d.grip(true);
  d.gripped[ev.slot] = d.t;
  d.wait(o.gripMs);
  const lift = ev.kind === "slip" ? 3 : 2;
  const up = d.go(o.liftMs, { head: gripHead(-lift) }, easeOut);
  d.shift(ev.slot, up.t0, up.t1, -lift, easeOut);
  d.wait(o.releaseMs * 2);
  if (ev.kind === "slip") {
    d.grip(false);
    // Falls home, bounces one row, lands.
    const fall = o.dropMs * 0.7;
    d.shift(ev.slot, d.t, d.t + fall, 0, easeIn);
    d.shift(ev.slot, d.t + fall, d.t + fall + 70, -1, easeOut);
    d.shift(ev.slot, d.t + fall + 70, d.t + fall + 140, 0, easeIn);
    d.placed[ev.slot] = d.t + fall + 140;
    d.go(o.dropMs * 1.6, { head: RAIL_HEAD - 4 }, easeIn);
    return d.script(0, d.t, INK);
  }
  const down = d.go(o.liftMs, { head: gripHead(0) }, easeInOut);
  d.shift(ev.slot, down.t0, down.t1, 0, easeInOut);
  d.grip(false);
  d.placed[ev.slot] = d.t;
  d.wait(o.releaseMs);
  d.go(o.dropMs * 1.6, { head: RAIL_HEAD - 4 }, easeIn);
  return d.script(0, d.t, INK);
}

function live(state: ClawState, tLive: number): Frame {
  const i = Math.floor(tLive / state.options.everyMs);
  for (const j of [i, i - 1]) {
    if (j < 0) continue;
    const ev = liveEvent(state, j);
    const dt = tLive - ev.at;
    const script = liveScript(state, ev);
    if (dt < 0 || dt >= Math.max(script.to, (script.placed[ev.slot] ?? 0) + state.options.flashMs)) continue;
    const frame = emptyFrame(state.width, state.height);
    paint(state, script, dt, frame);
    return frame;
  }
  return settled(state);
}
