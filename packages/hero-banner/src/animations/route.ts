import { emptyFrame, litCells, mulberry32, setPixel } from "../layout";
import type { Animation, Frame, Layout, Pixel } from "../types";

/**
 * ROUTE (digillm). Every pixel row is a lane to a provider.
 * LOADING: one request forks at the left edge and fans out: the centre lanes
 * leave first, the outer lanes branch later, so the stream heads form a `>`
 * chevron. Each lane runs at its own seeded speed (providers answer at
 * different latencies) and writes the letters it crosses at half strength.
 * When the last lane lands, the reply comes back as a `<` chevron, centre
 * first, and confirms every cell at full ink.
 * LIVE: single packets run along lanes, some fork into two lanes mid-flight;
 * one in four is a reply running back in `reply`. The word stays put.
 */

export type RouteOptions = {
  /** ms for a lane at speed 1 to cross the word. */
  crossMs: number;
  /** Extra delay per lane of distance from the centre: the fan's spread. */
  forkMs: number;
  /** Lane speeds are drawn from [1 - jitter, 1 + jitter]. */
  jitter: number;
  /** Pause between the last lane landing and the reply leaving. */
  holdMs: number;
  /** ms for the reply to cross the word. */
  returnMs: number;
  /** Strength of a cell the request has crossed but the reply has not. */
  pending: number;
  /** Empty-pixel trail behind a head, in pixels. */
  trail: number;
  /** LIVE: ms between packet launches. */
  packetEveryMs: number;
  /** LIVE: ms for a packet to cross the word. */
  packetMs: number;
};

type Lane = { y: number; depth: number; speed: number };

type Packet = { launch: number; lane: number; back: boolean; forkX: number | null; spread: number };

export type RouteState = {
  width: number;
  height: number;
  lit: Uint8Array;
  lanes: Lane[];
  seed: number;
  options: RouteOptions;
  outEndMs: number;
  returnStartMs: number;
  ms: number;
};

const ACCENT: Pixel = { tone: "accent", alpha: 1 };

export function routeAnimation(options: RouteOptions): Animation<RouteState> {
  return {
    kind: "route",
    liveTickMs: 50,
    prepare(layout: Layout, def) {
      const rand = mulberry32(def.seed);
      const lit = new Uint8Array(layout.width * layout.height);
      for (const cell of litCells(layout)) lit[cell.y * layout.width + cell.x] = 1;
      const centre = (layout.height - 1) / 2;
      const lanes: Lane[] = [];
      for (let y = 0; y < layout.height; y += 1) {
        const depth = Math.round(Math.abs(y - centre) - 0.5);
        lanes.push({ y, depth, speed: 1 - options.jitter + rand() * options.jitter * 2 });
      }
      const outEndMs = Math.max(...lanes.map((l) => l.depth * options.forkMs + options.crossMs / l.speed));
      const returnStartMs = outEndMs + options.holdMs;
      const maxDepth = Math.max(...lanes.map((l) => l.depth));
      // The reply clears the left edge (its 2-pixel flash included) before LOADING ends.
      const ms = Math.ceil(returnStartMs + maxDepth * options.forkMs + (options.returnMs * (layout.width + 2)) / layout.width);
      return { width: layout.width, height: layout.height, lit, lanes, seed: def.seed, options, outEndMs, returnStartMs, ms };
    },
    loadingMs: (state) => state.ms,
    loading,
    live,
    still: settled,
  };
}

const isLit = (state: RouteState, x: number, y: number) => state.lit[y * state.width + x] === 1;

/** x of a lane's request head at `t`; -Infinity before it forks. */
function requestHead(state: RouteState, lane: Lane, t: number): number {
  const local = t - lane.depth * state.options.forkMs;
  if (local < 0) return Number.NEGATIVE_INFINITY;
  return (local / state.options.crossMs) * lane.speed * state.width;
}

/** x of a lane's reply front at `t`; +Infinity before it leaves the right edge. */
function replyFront(state: RouteState, lane: Lane, t: number): number {
  const local = t - state.returnStartMs - lane.depth * state.options.forkMs;
  if (local < 0) return Number.POSITIVE_INFINITY;
  return state.width - 1 - (local / state.options.returnMs) * state.width;
}

function loading(state: RouteState, t: number): Frame {
  const frame = emptyFrame(state.width, state.height);
  const { pending, trail } = state.options;
  for (const lane of state.lanes) {
    const head = requestHead(state, lane, t);
    const reply = replyFront(state, lane, t);
    const landed = head >= state.width;
    for (let x = 0; x < state.width; x += 1) {
      const behind = head - x;
      if (behind < 0) break;
      if (isLit(state, x, lane.y)) {
        if (x >= reply + 2) setPixel(frame, x, lane.y, { tone: "ink", alpha: 1 });
        else if (x >= reply - 1 && Number.isFinite(reply)) setPixel(frame, x, lane.y, ACCENT);
        else if (behind < 2 && !landed) setPixel(frame, x, lane.y, ACCENT);
        else setPixel(frame, x, lane.y, { tone: "ink", alpha: pending });
      } else if (!landed && behind < trail) {
        // The stream itself: a fading trail on empty pixels, brightest at the head.
        setPixel(frame, x, lane.y, behind < 1 ? ACCENT : { tone: "accent", alpha: 0.4 * (1 - behind / trail) });
      } else if (Number.isFinite(reply) && x >= reply - 1 && x < reply + 1) {
        setPixel(frame, x, lane.y, { tone: "accent", alpha: 0.35 });
      }
    }
  }
  return frame;
}

function settled(state: RouteState): Frame {
  const frame = emptyFrame(state.width, state.height);
  for (let y = 0; y < state.height; y += 1) {
    for (let x = 0; x < state.width; x += 1) if (isLit(state, x, y)) setPixel(frame, x, y, { tone: "ink", alpha: 1 });
  }
  return frame;
}

/** Packet `i` of the LIVE schedule. Seeded per index, so any moment can be sampled. */
function packet(state: RouteState, i: number): Packet {
  const rand = mulberry32((state.seed ^ Math.imul(i + 1, 0x9e3779b1)) >>> 0);
  const { packetEveryMs } = state.options;
  const launch = i * packetEveryMs + Math.floor(rand() * packetEveryMs * 0.6);
  const lane = Math.floor(rand() * state.height);
  const back = rand() < 0.25;
  const forks = !back && rand() < 0.4;
  const forkX = forks ? Math.floor(state.width * (0.25 + rand() * 0.45)) : null;
  const spread = 1 + Math.floor(rand() * 3);
  return { launch, lane, back, forkX, spread };
}

function paintComet(state: RouteState, frame: Frame, y: number, head: number, dir: 1 | -1, tone: string, fromX: number): void {
  if (y < 0 || y >= state.height) return;
  const trail = state.options.trail;
  for (let k = 0; k < trail; k += 1) {
    const x = Math.round(head) - dir * k;
    if (dir === 1 ? x < fromX : x > fromX) break;
    if (x < 0 || x >= state.width) continue;
    if (isLit(state, x, y)) {
      if (k < 2) setPixel(frame, x, y, { tone, alpha: 1 });
    } else {
      setPixel(frame, x, y, { tone, alpha: k === 0 ? 1 : 0.45 * (1 - k / trail) });
    }
  }
}

function live(state: RouteState, tLive: number): Frame {
  const frame = settled(state);
  const { packetEveryMs, packetMs, trail } = state.options;
  const life = packetMs + (trail / state.width) * packetMs;
  const first = Math.max(0, Math.floor((tLive - life) / packetEveryMs) - 1);
  const last = Math.floor(tLive / packetEveryMs);
  for (let i = first; i <= last; i += 1) {
    const p = packet(state, i);
    const age = tLive - p.launch;
    if (age < 0 || age > life) continue;
    const travel = (age / packetMs) * state.width;
    if (p.back) {
      paintComet(state, frame, p.lane, state.width - 1 - travel, -1, "reply", state.width - 1);
    } else if (p.forkX != null && travel > p.forkX) {
      // Routed: the packet splits into two lanes at forkX.
      paintComet(state, frame, p.lane, p.forkX, 1, "accent", 0);
      const up = p.lane - p.spread >= 0 ? p.lane - p.spread : p.lane + p.spread + 1;
      const down = p.lane + p.spread < state.height ? p.lane + p.spread : p.lane - p.spread - 1;
      paintComet(state, frame, up, travel, 1, "accent", p.forkX);
      paintComet(state, frame, down, travel, 1, "accent", p.forkX);
    } else {
      paintComet(state, frame, p.lane, travel, 1, "accent", 0);
    }
  }
  return frame;
}
