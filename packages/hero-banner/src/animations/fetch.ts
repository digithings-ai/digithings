import { emptyFrame, litCells, mulberry32, setPixel } from "../layout";
import type { Animation, Frame, Layout } from "../types";

/**
 * FETCH (digifetch). The word is downloaded, not drawn.
 * LOADING: a request leaves first: one `glint` pixel with an `accent` tail runs
 * left to right along the middle row and out of the right edge. Then the
 * response streams back. Every lit cell of the word is a packet that enters at
 * the right edge on its own row and travels left until it reaches its home
 * cell; it lands as a short `glint` flash, then `ink`. Packets for the left
 * columns leave first and travel furthest, so each row is a steady stream
 * pulled in from off screen and the word fills from left to right.
 * LIVE: the page is fetched again now and then. A request runs out along one
 * row, and a small burst of packets returns on that row and its neighbours,
 * each landing on a cell of the word with a `glint` flash.
 */

export type FetchOptions = {
  /** ms per pixel column for a request pixel. */
  requestColMs: number;
  /** ms per pixel column for a response packet. */
  packetColMs: number;
  /** LOADING: launch delay per home column (left columns launch first). */
  launchColMs: number;
  /** LOADING: random extra launch delay per packet, below `launchColMs`. */
  jitterMs: number;
  /** ms a landed packet shows `glint` before it settles to `ink`. */
  flashMs: number;
  /** `accent` alpha of the trail cells behind a moving pixel, nearest first. */
  tail: number[];
  /** LIVE: ms between fetches. */
  everyMs: number;
  /** LIVE: packets per fetch, [min, max]. */
  burst: [number, number];
};

/** A packet: travels left along row `y` from the right edge to `x`. */
export type Packet = { x: number; y: number; launch: number; land: number };

export type FetchState = {
  width: number;
  height: number;
  lit: Uint8Array;
  cells: { x: number; y: number }[];
  /** LOADING packets, one per lit cell. */
  packets: Packet[];
  /** LOADING: when the request pixel has left the right edge. */
  requestMs: number;
  seed: number;
  options: FetchOptions;
  ms: number;
};

export function fetchAnimation(options: FetchOptions): Animation<FetchState> {
  return {
    kind: "fetch",
    liveTickMs: 40,
    prepare(layout: Layout, def) {
      const { width, height } = layout;
      const rand = mulberry32(def.seed);
      const lit = new Uint8Array(width * height);
      const cells = litCells(layout).map(({ x, y }) => ({ x, y }));
      for (const c of cells) lit[c.y * width + c.x] = 1;
      const requestMs = (width + options.tail.length) * options.requestColMs;
      const packets = cells.map(({ x, y }) => {
        const launch = Math.round(requestMs + x * options.launchColMs + rand() * options.jitterMs);
        return { x, y, launch, land: launch + travel(width, x, options.packetColMs) };
      });
      const ms = Math.max(...packets.map((p) => p.land)) + options.flashMs;
      return { width, height, lit, cells, packets, requestMs, seed: def.seed, options, ms };
    },
    loadingMs: (state) => state.ms,
    loading,
    live,
    still: settled,
  };
}

/** ms a packet takes from the right edge to column `x`. */
const travel = (width: number, x: number, colMs: number) => (width - 1 - x) * colMs;

/** Paint a moving pixel at column `head` on row `y` with its tail on the side
 *  it came from (`dir` is +1 moving right, -1 moving left). Lit cells under the
 *  tail keep their ink. */
function paintMover(state: FetchState, frame: Frame, head: number, y: number, dir: 1 | -1): void {
  const { width, lit, options } = state;
  options.tail.forEach((alpha, i) => {
    const x = head - dir * (i + 1);
    if (x >= 0 && x < width && !lit[y * width + x]) setPixel(frame, x, y, { tone: "accent", alpha });
  });
  if (head >= 0 && head < width) setPixel(frame, head, y, { tone: "glint", alpha: 1 });
}

/** Paint packet `p` at `t`: moving, flashing on landing, or settled ink. */
function paintPacket(state: FetchState, frame: Frame, p: Packet, t: number): void {
  if (t < p.launch) return;
  if (t < p.land) {
    paintMover(state, frame, state.width - 1 - Math.floor((t - p.launch) / state.options.packetColMs), p.y, -1);
  } else {
    const flash = t < p.land + state.options.flashMs;
    setPixel(frame, p.x, p.y, { tone: flash ? "glint" : "ink", alpha: 1 });
  }
}

function loading(state: FetchState, t: number): Frame {
  const frame = emptyFrame(state.width, state.height);
  const { requestColMs } = state.options;
  if (t < state.requestMs) paintMover(state, frame, Math.floor(t / requestColMs), state.height >> 1, 1);
  // Landed cells first, so packets in flight draw over them.
  const order = [...state.packets].sort((a, b) => Number(t < a.land) - Number(t < b.land));
  for (const p of order) paintPacket(state, frame, p, t);
  return frame;
}

function settled(state: FetchState): Frame {
  const frame = emptyFrame(state.width, state.height);
  for (let i = 0; i < state.lit.length; i += 1) if (state.lit[i]) frame.pixels[i] = { tone: "ink", alpha: 1 };
  return frame;
}

/** LIVE fetch `i`, seeded per index so any moment can be sampled: the request
 *  row, when it starts, and the packets of its response. */
export function liveFetch(state: FetchState, i: number): { y: number; at: number; packets: Packet[] } {
  const rand = mulberry32((state.seed ^ Math.imul(i + 1, 0x9e3779b1)) >>> 0);
  const { width, height, cells, options } = state;
  const at = i * options.everyMs + Math.floor(rand() * options.everyMs * 0.3);
  const y = 1 + Math.floor(rand() * Math.max(1, height - 2));
  const back = at + (width + options.tail.length) * options.requestColMs;
  const rows = cells.filter((c) => Math.abs(c.y - y) <= 1);
  const n = options.burst[0] + Math.floor(rand() * (options.burst[1] - options.burst[0] + 1));
  const packets: Packet[] = [];
  for (let k = 0; k < n && rows.length > 0; k += 1) {
    const c = rows[Math.floor(rand() * rows.length)];
    const launch = back + Math.floor(rand() * 6) * options.packetColMs * 2;
    packets.push({ x: c.x, y: c.y, launch, land: launch + travel(width, c.x, options.packetColMs) });
  }
  return { y, at, packets };
}

function live(state: FetchState, tLive: number): Frame {
  const frame = settled(state);
  const { width, options } = state;
  const span = (width + options.tail.length) * options.requestColMs + 12 * options.packetColMs + width * options.packetColMs + options.flashMs;
  const first = Math.max(0, Math.floor((tLive - span) / options.everyMs) - 1);
  const last = Math.floor(tLive / options.everyMs);
  for (let i = first; i <= last; i += 1) {
    const f = liveFetch(state, i);
    const head = Math.floor((tLive - f.at) / options.requestColMs);
    if (tLive >= f.at && head < width + options.tail.length) paintMover(state, frame, head, f.y, 1);
    for (const p of f.packets) if (tLive < p.land + options.flashMs) paintPacket(state, frame, p, tLive);
  }
  return frame;
}
