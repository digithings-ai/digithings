import { emptyFrame, litCells, mulberry32, setPixel } from "../layout";
import type { Animation, Frame, Layout, Pixel } from "../types";

/**
 * TYPE (digidev). The word is typed at a prompt, then built.
 * LOADING: a block cursor (`accent`) blinks on the first slot, then the word is
 * typed one glyph per keystroke at a human, uneven pace. A glyph under the
 * cursor shows in inverse video (the block lit, the glyph cut out of it), as a
 * terminal does. One seeded keystroke is a typo: a wrong glyph lands, the
 * cursor waits, backspaces and retypes. Typed glyphs sit in `accent` (source,
 * not yet built). The cursor parks on the last glyph and blinks, then a build
 * sweep (`glint` band) runs left to right and turns the source into ink.
 * LIVE: an edit loop. Every so often the cursor jumps to one glyph, deletes it,
 * retypes it and a short sweep rebuilds it; one event in three is a full
 * rebuild sweep over the whole word instead.
 */

export type TypeOptions = {
  /** LOADING: ms the cursor blinks on the empty first slot before typing. */
  idleMs: number;
  /** Mean ms between keystrokes. */
  keyMs: number;
  /** Keystroke jitter, as a share of `keyMs` (0..1). */
  jitter: number;
  /** ms the typo stays before the backspace. */
  typoMs: number;
  /** ms the cursor blinks on the last glyph before the build. */
  holdMs: number;
  /** ms of the build sweep over the whole word. */
  buildMs: number;
  /** Cursor blink period (on + off). */
  blinkMs: number;
  /** LIVE: ms between edit events. */
  everyMs: number;
};

/** A keystroke: at `at`, slot `slot` gets `char` (null is a backspace that clears it). */
export type Key = { at: number; slot: number; char: string | null };

export type TypeState = {
  width: number;
  height: number;
  layout: Layout;
  /** Per glyph slot, the cells of its correct glyph. */
  cells: { x: number; y: number }[][];
  keys: Key[];
  /** End of typing; the cursor blinks on the last slot from here. */
  typedAt: number;
  /** Start of the build sweep. */
  buildAt: number;
  seed: number;
  options: TypeOptions;
  ms: number;
};

const TYPO_CHARS = "XKQZWV";

export function typeAnimation(options: TypeOptions): Animation<TypeState> {
  return {
    kind: "type",
    liveTickMs: 40,
    prepare(layout: Layout, def) {
      const { width, height } = layout;
      const rand = mulberry32(def.seed);
      const n = layout.text.length;
      const cells: { x: number; y: number }[][] = Array.from({ length: n }, () => []);
      for (const c of litCells(layout)) cells[c.glyph].push({ x: c.x, y: c.y });
      const typoSlot = n > 3 ? 2 + Math.floor(rand() * (n - 3)) : -1;
      const typoChoices = [...TYPO_CHARS].filter((ch) => ch !== layout.text[typoSlot] && layout.font.glyphs[ch]);
      const typoChar = typoChoices[Math.floor(rand() * typoChoices.length)] ?? null;
      const gap = () => Math.round(options.keyMs * (1 + options.jitter * (2 * rand() - 1)));
      const keys: Key[] = [];
      let at = options.idleMs;
      for (let slot = 0; slot < n; slot += 1) {
        if (slot === typoSlot && typoChar) {
          keys.push({ at, slot, char: typoChar });
          at += options.typoMs;
          keys.push({ at, slot, char: null });
          at += gap();
        }
        keys.push({ at, slot, char: layout.text[slot] ?? null });
        if (slot < n - 1) at += gap();
      }
      const typedAt = at;
      const buildAt = typedAt + options.holdMs;
      const ms = buildAt + options.buildMs;
      return { width, height, layout, cells, keys, typedAt, buildAt, seed: def.seed, options, ms };
    },
    loadingMs: (state) => state.ms,
    loading,
    live,
    still: settled,
  };
}

const blinkOn = (state: TypeState, t: number) => t % state.options.blinkMs < state.options.blinkMs / 2;

/** Cells of `char` drawn in slot `slot` of the layout. */
function glyphCells(state: TypeState, slot: number, char: string): { x: number; y: number }[] {
  if (char === state.layout.text[slot]) return state.cells[slot];
  const glyph = state.layout.font.glyphs[char];
  const x0 = state.layout.starts[slot] ?? 0;
  const out: { x: number; y: number }[] = [];
  for (let y = 0; y < state.height; y += 1) {
    const row = glyph?.[y] ?? "";
    for (let c = 0; c < state.layout.font.cols; c += 1) if (row[c] === "#") out.push({ x: x0 + c, y });
  }
  return out;
}

/** Block cursor over slot `slot`: lit everywhere except where `under` has a glyph. */
function drawCursor(state: TypeState, frame: Frame, slot: number, under: string | null) {
  const x0 = state.layout.starts[slot] ?? 0;
  const cut = new Set(under ? glyphCells(state, slot, under).map((c) => c.y * state.width + c.x) : []);
  for (let y = 0; y < state.height; y += 1) {
    for (let c = 0; c < state.layout.font.cols; c += 1) {
      const i = y * state.width + x0 + c;
      frame.pixels[i] = cut.has(i) ? null : { tone: "accent", alpha: 0.9 };
    }
  }
}

/** Build sweep at progress `p`: columns behind the band are ink, the band is glint. */
function sweep(p: number, x: number, from: number, to: number): Pixel | null | "source" {
  const head = from + p * (to - from + 3);
  if (x < head - 2) return null;
  if (x < head) return { tone: "glint", alpha: 1 };
  return "source";
}

const SOURCE: Pixel = { tone: "accent", alpha: 0.75 };
const INK: Pixel = { tone: "ink", alpha: 1 };

function loading(state: TypeState, t: number): Frame {
  const frame = emptyFrame(state.width, state.height);
  const typed: (string | null)[] = state.layout.text.split("").map(() => null);
  let cursor = 0;
  for (const key of state.keys) {
    if (key.at > t) break;
    typed[key.slot] = key.char;
    // A keystroke moves the cursor on; a backspace leaves it on the cleared slot.
    cursor = key.char === null ? key.slot : Math.min(key.slot + 1, typed.length - 1);
  }
  if (t >= state.buildAt) {
    const p = Math.min(1, (t - state.buildAt) / state.options.buildMs);
    for (const slot of state.cells) {
      for (const c of slot) {
        const s = sweep(p, c.x, 0, state.width);
        setPixel(frame, c.x, c.y, s === null ? INK : s === "source" ? SOURCE : s);
      }
    }
    return frame;
  }
  typed.forEach((ch, slot) => {
    if (ch) for (const c of glyphCells(state, slot, ch)) setPixel(frame, c.x, c.y, SOURCE);
  });
  // While keys come in the cursor stays solid; idle, it blinks.
  const lastKey = state.keys.filter((k) => k.at <= t).at(-1);
  const idle = !lastKey || t - lastKey.at > state.options.blinkMs;
  if (!idle || blinkOn(state, t)) drawCursor(state, frame, cursor, typed[cursor]);
  return frame;
}

function settled(state: TypeState): Frame {
  const frame = emptyFrame(state.width, state.height);
  for (const slot of state.cells) for (const c of slot) setPixel(frame, c.x, c.y, INK);
  return frame;
}

export type EditEvent = { at: number; kind: "edit" | "rebuild"; slot: number };

/** LIVE event `i`, seeded per index so any moment can be sampled. */
export function liveEvent(state: TypeState, i: number): EditEvent {
  const rand = mulberry32((state.seed ^ Math.imul(i + 1, 0x9e3779b1)) >>> 0);
  const { everyMs } = state.options;
  const at = i * everyMs + Math.floor(rand() * everyMs * 0.4);
  const kind = rand() < 1 / 3 ? "rebuild" : "edit";
  const slot = Math.floor(rand() * state.cells.length);
  return { at, kind, slot };
}

/** Phases of an edit, in ms from its start: cursor jumps and blinks, the glyph
 *  is deleted, retyped, then rebuilt by a short sweep. */
function editSpan(state: TypeState) {
  const { blinkMs, keyMs, typoMs } = state.options;
  const del = blinkMs;
  const retype = del + typoMs;
  const build = retype + keyMs + blinkMs / 2;
  const end = build + 360;
  return { del, retype, build, end };
}

function live(state: TypeState, tLive: number): Frame {
  const frame = settled(state);
  const i = Math.floor(tLive / state.options.everyMs);
  for (const j of [i - 1, i]) {
    if (j < 0) continue;
    const ev = liveEvent(state, j);
    const dt = tLive - ev.at;
    if (ev.kind === "rebuild") {
      const p = dt / state.options.buildMs;
      if (p <= 0 || p >= 1) continue;
      for (const slot of state.cells) {
        for (const c of slot) {
          const s = sweep(p, c.x, 0, state.width);
          if (s !== null) setPixel(frame, c.x, c.y, s === "source" ? INK : s);
        }
      }
      continue;
    }
    const span = editSpan(state);
    if (dt <= 0 || dt >= span.end) continue;
    const slot = ev.slot;
    const x0 = state.layout.starts[slot] ?? 0;
    const x1 = x0 + state.layout.font.cols - 1;
    if (dt < span.build) {
      for (const c of state.cells[slot]) setPixel(frame, c.x, c.y, dt < span.del ? INK : dt < span.retype ? null : SOURCE);
      const under = dt < span.del || dt >= span.retype ? state.layout.text[slot] ?? null : null;
      if (dt < span.retype || blinkOn(state, dt)) drawCursor(state, frame, slot, under);
    } else {
      const p = (dt - span.build) / (span.end - span.build);
      for (const c of state.cells[slot]) {
        const s = sweep(p, c.x, x0, x1);
        setPixel(frame, c.x, c.y, s === null ? INK : s === "source" ? SOURCE : s);
      }
    }
  }
  return frame;
}
