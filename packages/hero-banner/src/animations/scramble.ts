import { emptyFrame, setPixel } from "../layout";
import type { Animation, Frame, Layout } from "../types";

/**
 * SCRAMBLE (digichat). LOADING: every slot spins through random glyphs in the
 * dim tone, then locks left to right with a flash. LIVE: the settled word rests;
 * one letter flashes after a long quiet stretch. Characters never scramble again.
 * Port of packages/ui/src/components/chat/digichat-wordmark.ts (slotsAt,
 * idleSlots): same timing constants, same hash.
 */

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
};

export type ScrambleState = { layout: Layout; options: ScrambleOptions; cycleMs: number };

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
  return {
    kind: "scramble",
    liveTickMs: 100,
    prepare(layout) {
      return { layout, options, cycleMs: options.spinMs + layout.text.length * options.lockMs + options.holdMs };
    },
    loadingMs: (state) => state.cycleMs,
    loading: (state, t) => draw(state, slotsAt(state, t)),
    live: (state, tLive) => draw(state, idleSlots(state, tLive)),
    still: (state) => draw(state, slotsAt(state, state.options.settledMs)),
  };
}
