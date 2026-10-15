import { emptyFrame, mulberry32, setPixel } from "../layout";
import type { Animation, Frame, Layout } from "../types";

/**
 * SCRAMBLE (digichat). LOADING: every slot spins through random glyphs in the
 * dim tone, then locks left to right with a flash. Characters never scramble again.
 * LIVE is one of:
 * - `flash`: the settled word rests; one letter flashes after a long quiet
 *   stretch. Port of packages/ui/src/components/chat/digichat-wordmark.ts
 *   (slotsAt, idleSlots): same timing constants, same hash.
 * - `stream`: after a quiet stretch the word re-streams. It drops to its dim
 *   ghost, then comes back left to right in tokens of 1-3 letters at uneven
 *   latencies, each token landing with a flash, like a reply streaming in.
 *   The split and latencies change every pass (seeded), and every letter is
 *   always the right glyph.
 */

export type StreamOptions = {
  /** Settled rest before each pass. */
  quietMs: number;
  /** Delay from one token to the next: uniform in [min, max]. */
  tokenMs: readonly [number, number];
  /** Longest token, in letters. */
  maxToken: number;
};

export type ScrambleOptions = {
  stepMs: number;
  spinMs: number;
  lockMs: number;
  holdMs: number;
  flashMs: number;
  /** Inside the hold, after the last lock flash: the settled moment. */
  settledMs: number;
  idleGapMs: number;
  pool: string;
  /** LIVE motion. Defaults to `flash` (the legacy idle). */
  live?: { kind: "flash" } | ({ kind: "stream" } & StreamOptions);
};

export type ScrambleState = {
  layout: Layout;
  options: ScrambleOptions;
  cycleMs: number;
  seed: number;
  /** One stream pass slot: quiet, then the longest possible pass. */
  streamPeriodMs: number;
};

type Slot = { ch: string | null; tone: "dim" | "rest" | "flash" };

function poolChar(state: ScrambleState, slot: number, step: number): string | null {
  const { pool } = state.options;
  let x = Math.imul(step + 1, 0x9e3779b1) ^ Math.imul(slot + 1, 0x85ebca6b);
  x = Math.imul(x ^ (x >>> 16), 0x7feb352d);
  x = (x ^ (x >>> 15)) >>> 0;
  for (let i = 0; i < pool.length; i += 1) {
    const ch = pool[(x + i) % pool.length];
    if (ch && state.layout.font.glyphs[ch]) return ch;
  }
  return null;
}

function slotsAt(state: ScrambleState, tMs: number): Slot[] {
  const { spinMs, lockMs, stepMs, flashMs } = state.options;
  const t = Number.isFinite(tMs) ? Math.max(0, Math.floor(tMs)) : 0;
  const text = state.layout.text;
  const slots: Slot[] = [];
  for (let slot = 0; slot < text.length; slot += 1) {
    const lockAt = spinMs + slot * lockMs;
    if (t < lockAt) {
      slots.push({ ch: poolChar(state, slot, Math.floor(t / stepMs)), tone: "dim" });
      continue;
    }
    slots.push({ ch: text[slot] ?? null, tone: t < lockAt + flashMs ? "flash" : "rest" });
  }
  return slots;
}

function idleSlots(state: ScrambleState, idle: number): Slot[] {
  const base = slotsAt(state, state.options.settledMs);
  const span = state.options.idleGapMs + state.options.flashMs;
  const elapsed = Number.isFinite(idle) ? Math.max(0, idle) : 0;
  if (elapsed % span < state.options.idleGapMs) return base;
  const index = Math.floor(elapsed / span) % Math.max(1, base.length);
  return base.map((slot, i) => (i === index ? { ch: slot.ch, tone: "flash" } : slot));
}

/** Landing time of each letter in one pass, ms after the pass starts. Pure in (seed, pass). */
export function streamPass(state: ScrambleState, pass: number): number[] {
  const live = state.options.live;
  const n = state.layout.text.length;
  if (live?.kind !== "stream") return new Array<number>(n).fill(0);
  const rand = mulberry32((state.seed ^ Math.imul(pass + 1, 0x9e3779b1)) | 0);
  const [lo, hi] = live.tokenMs;
  const landAt: number[] = [];
  let at = lo;
  while (landAt.length < n) {
    const size = 1 + Math.floor(rand() * Math.max(1, live.maxToken));
    for (let i = 0; i < size && landAt.length < n; i += 1) landAt.push(at);
    at += Math.round(lo + rand() * (hi - lo));
  }
  return landAt;
}

function streamSlots(state: ScrambleState, tLive: number): Slot[] {
  const live = state.options.live;
  const base = slotsAt(state, state.options.settledMs);
  if (live?.kind !== "stream") return base;
  const t = Number.isFinite(tLive) ? Math.max(0, tLive) : 0;
  const p = (t % state.streamPeriodMs) - live.quietMs;
  if (p < 0) return base;
  const landAt = streamPass(state, Math.floor(t / state.streamPeriodMs));
  return base.map((slot, i) => {
    const at = landAt[i] ?? 0;
    if (p < at) return { ch: slot.ch, tone: "dim" };
    if (p < at + state.options.flashMs) return { ch: slot.ch, tone: "flash" };
    return slot;
  });
}

function draw(state: ScrambleState, slots: Slot[]): Frame {
  const { layout } = state;
  const frame = emptyFrame(layout.width, layout.height);
  slots.forEach((slot, i) => {
    const glyph = slot.ch ? layout.font.glyphs[slot.ch] : undefined;
    if (!glyph) return;
    const x0 = layout.starts[i] ?? 0;
    for (let y = 0; y < layout.height; y += 1) {
      const row = glyph[y] ?? "";
      for (let c = 0; c < layout.font.cols; c += 1) {
        if (row[c] === "#") setPixel(frame, x0 + c, y, { tone: slot.tone, alpha: 1 });
      }
    }
  });
  return frame;
}

export function scrambleAnimation(options: ScrambleOptions): Animation<ScrambleState> {
  const stream = options.live?.kind === "stream" ? options.live : null;
  return {
    kind: "scramble",
    // Token latencies are 70-190 ms; a 100 ms tick would blur them together.
    liveTickMs: stream ? 40 : 100,
    prepare(layout, def) {
      const n = layout.text.length;
      return {
        layout,
        options,
        cycleMs: options.spinMs + n * options.lockMs + options.holdMs,
        seed: def.seed,
        streamPeriodMs: stream ? stream.quietMs + n * stream.tokenMs[1] + options.flashMs : 1,
      };
    },
    loadingMs: (state) => state.cycleMs,
    loading: (state, t) => draw(state, slotsAt(state, t)),
    live: (state, tLive) => draw(state, stream ? streamSlots(state, tLive) : idleSlots(state, tLive)),
    still: (state) => draw(state, slotsAt(state, state.options.settledMs)),
  };
}
