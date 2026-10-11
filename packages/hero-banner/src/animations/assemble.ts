import { emptyFrame, litCells, mulberry32, setPixel } from "../layout";
import type { Animation, Frame, Layout, Pixel } from "../types";

/**
 * ASSEMBLE (digithings). Every lit cell is a part; every letter is a thing
 * made of parts.
 * LOADING: letter by letter, left to right, a letter's socket shows faintly
 * and its parts fly in from a seeded cloud around it, eased, in the accent.
 * A part flashes as it seats, then cools to ink. The clouds overlap, so a
 * swarm travels along the word and condenses into it.
 * LIVE: now and then a few parts of one letter lift out, hang, and seat
 * again. Their sockets stay faint, so the word always reads.
 */

export type AssembleOptions = {
  /** Delay before the first letter's parts leave. */
  startMs: number;
  /** Delay between one letter and the next. */
  letterMs: number;
  /** Random extra launch delay per part, in [0, spreadMs). */
  spreadMs: number;
  /** Flight time of a part; each part draws from [1 - jitter, 1 + jitter] x flyMs. */
  flyMs: number;
  jitter: number;
  /** Horizontal radius, in pixels, of the cloud a letter's parts start from. */
  cloud: number;
  /** Accent flash when a part seats. */
  seatMs: number;
  /** Strength of an empty socket. */
  socket: number;
  /** LIVE: ms between lifts. */
  liftEveryMs: number;
  /** LIVE: parts per lift, [min, max]. */
  liftParts: readonly [number, number];
  /** LIVE: out, hang and back times of a lift. */
  liftOutMs: number;
  liftHoldMs: number;
  liftBackMs: number;
};

type Part = { x: number; y: number; glyph: number; sx: number; sy: number; launch: number; land: number };

export type AssembleState = {
  width: number;
  height: number;
  parts: Part[];
  /** Part indices per glyph. */
  glyphs: number[][];
  /** When each glyph's socket shows: its first part's launch. */
  socketAt: number[];
  seed: number;
  options: AssembleOptions;
  ms: number;
};

type Lift = { start: number; moves: { part: number; dx: number; dy: number }[] };

const INK: Pixel = { tone: "ink", alpha: 1 };
const ACCENT: Pixel = { tone: "accent", alpha: 1 };

const easeOut = (p: number) => 1 - (1 - p) ** 3;
const easeOutQuad = (p: number) => 1 - (1 - p) ** 2;
const easeInOut = (p: number) => (p < 0.5 ? 4 * p ** 3 : 1 - (-2 * p + 2) ** 3 / 2);
const clamp = (v: number, lo: number, hi: number) => Math.min(hi, Math.max(lo, v));

export function assembleAnimation(options: AssembleOptions): Animation<AssembleState> {
  return {
    kind: "assemble",
    liveTickMs: 50,
    prepare(layout: Layout, def) {
      const rand = mulberry32(def.seed);
      const cols = layout.font.cols;
      const parts: Part[] = litCells(layout).map((cell) => {
        const centre = (layout.starts[cell.glyph] ?? 0) + (cols - 1) / 2;
        const sx = clamp(Math.round(centre + (rand() * 2 - 1) * options.cloud), 0, layout.width - 1);
        const sy = Math.floor(rand() * layout.height);
        const launch = options.startMs + cell.glyph * options.letterMs + Math.floor(rand() * options.spreadMs);
        const fly = options.flyMs * (1 - options.jitter + rand() * options.jitter * 2);
        return { x: cell.x, y: cell.y, glyph: cell.glyph, sx, sy, launch, land: Math.round(launch + fly) };
      });
      const glyphs: number[][] = layout.text.split("").map(() => []);
      parts.forEach((p, i) => glyphs[p.glyph]?.push(i));
      const socketAt = glyphs.map((ids) => Math.min(...ids.map((i) => parts[i]!.launch)));
      const ms = Math.max(0, ...parts.map((p) => p.land + options.seatMs));
      return { width: layout.width, height: layout.height, parts, glyphs, socketAt, seed: def.seed, options, ms };
    },
    loadingMs: (state) => state.ms,
    loading,
    live,
    still: settled,
  };
}

function settled(state: AssembleState): Frame {
  const frame = emptyFrame(state.width, state.height);
  for (const p of state.parts) setPixel(frame, p.x, p.y, INK);
  return frame;
}

function loading(state: AssembleState, t: number): Frame {
  const frame = emptyFrame(state.width, state.height);
  const { seatMs, socket } = state.options;
  const socketPx: Pixel = { tone: "ink", alpha: socket };
  // Sockets and seated parts first, so parts in flight draw over them.
  for (const p of state.parts) {
    if (t >= p.land) setPixel(frame, p.x, p.y, t < p.land + seatMs ? ACCENT : INK);
    else if (t >= (state.socketAt[p.glyph] ?? Infinity)) setPixel(frame, p.x, p.y, socketPx);
  }
  for (const p of state.parts) {
    if (t < p.launch || t >= p.land) continue;
    // Quadratic, not cubic: a part keeps moving until it seats instead of
    // parking on its socket in the accent.
    const k = easeOutQuad((t - p.launch) / (p.land - p.launch));
    setPixel(frame, Math.round(p.sx + (p.x - p.sx) * k), Math.round(p.sy + (p.y - p.sy) * k), ACCENT);
  }
  return frame;
}

/** Lift `i` of the LIVE schedule. Seeded per index, so any moment can be sampled. */
function lift(state: AssembleState, i: number): Lift {
  const rand = mulberry32((state.seed ^ Math.imul(i + 1, 0x9e3779b1)) >>> 0);
  const { liftEveryMs, liftParts } = state.options;
  const start = i * liftEveryMs + Math.floor(rand() * liftEveryMs * 0.5);
  const ids = state.glyphs[Math.floor(rand() * state.glyphs.length)] ?? [];
  const n = Math.min(ids.length, liftParts[0] + Math.floor(rand() * (liftParts[1] - liftParts[0] + 1)));
  // One direction for the whole lift, so the parts move as a group.
  const dirX = rand() < 0.5 ? -1 : 1;
  const dirY = rand() < 0.5 ? -1 : 1;
  const picked = new Set<number>();
  while (picked.size < n) picked.add(ids[Math.floor(rand() * ids.length)]!);
  const moves = [...picked].map((part) => ({
    part,
    dx: dirX * (2 + Math.floor(rand() * 5)),
    dy: dirY * Math.floor(rand() * 3),
  }));
  return { start, moves };
}

function live(state: AssembleState, tLive: number): Frame {
  const frame = settled(state);
  const { liftEveryMs, liftOutMs, liftHoldMs, liftBackMs, seatMs, socket } = state.options;
  const life = liftOutMs + liftHoldMs + liftBackMs + seatMs;
  const socketPx: Pixel = { tone: "ink", alpha: socket };
  const first = Math.max(0, Math.floor((tLive - life) / liftEveryMs) - 1);
  const last = Math.floor(tLive / liftEveryMs);
  const flying: [number, number][] = [];
  for (let i = first; i <= last; i += 1) {
    const l = lift(state, i);
    const age = tLive - l.start;
    if (age < 0 || age >= life) continue;
    for (const m of l.moves) {
      const p = state.parts[m.part]!;
      if (age >= liftOutMs + liftHoldMs + liftBackMs) {
        setPixel(frame, p.x, p.y, ACCENT);
        continue;
      }
      const k =
        age < liftOutMs
          ? easeOut(age / liftOutMs)
          : age < liftOutMs + liftHoldMs
            ? 1
            : 1 - easeInOut((age - liftOutMs - liftHoldMs) / liftBackMs);
      setPixel(frame, p.x, p.y, socketPx);
      flying.push([Math.round(p.x + m.dx * k), Math.round(p.y + m.dy * k)]);
    }
  }
  for (const [x, y] of flying) setPixel(frame, x, y, ACCENT);
  return frame;
}
