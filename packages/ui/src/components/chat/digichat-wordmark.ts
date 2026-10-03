/**
 * DIGICHAT block wordmark.
 *
 * Glyph cells are 7×10. A terminal cell is about twice as tall as it is wide,
 * so the TUI draws with half-blocks (▀ ▄ █), the same method as
 * digivoice/tui/src/hero.js. D, I, G, C, H, and T are that file's bitmaps.
 * Gaps stay empty. One color mode per cell: 38;2 only when truecolor is on,
 * otherwise 38;5. Never both.
 *
 * The settled word is the mark. The scramble is how it plays.
 */

export const WORD = "DIGICHAT";
export const STEP_MS = 80;
export const SPIN_MS = 240;
export const LOCK_MS = 180;
export const HOLD_MS = 960;
export const FLASH_MS = 200;
/** SPIN + 8 * LOCK + HOLD = 2.64s. */
export const CYCLE_MS = SPIN_MS + 8 * LOCK_MS + HOLD_MS;
/** Inside the hold, after the last lock flash. */
export const SETTLED_MS = 2000;

export const POOL = "ABCDEFGHIJKLMNOPQRSTUVWXYZ0123456789!?#$%&*+-=/<>().,:;@";

export const SHADES = {
  dim: { rgb: 95, cube: 59 },
  rest: { rgb: 215, cube: 188 },
  flash: { rgb: 255, cube: 231 },
} as const;

export type ShadeName = keyof typeof SHADES;
export type CellColor = { rgb: number } | { cube: number };

export type WordCell = {
  ch: string;
  color: CellColor | null;
};

export type SlotFrame = {
  ch: string | null;
  shade: ShadeName;
};

const GLYPHS: Record<string, readonly string[]> = {
  A: ["..###..", ".#####.", "##...##", "##...##", "#######", "#######", "##...##", "##...##", "##...##", "##...##"],
  B: ["######.", "#######", "##...##", "##...##", "######.", "######.", "##...##", "##...##", "#######", "######."],
  C: [".#####.", "#######", "##.....", "##.....", "##.....", "##.....", "##.....", "##.....", "#######", ".#####."],
  D: ["######.", "#######", "##...##", "##...##", "##...##", "##...##", "##...##", "##...##", "#######", "######."],
  E: ["#######", "#######", "##.....", "##.....", "######.", "######.", "##.....", "##.....", "#######", "#######"],
  F: ["#######", "#######", "##.....", "##.....", "######.", "######.", "##.....", "##.....", "##.....", "##....."],
  G: [".#####.", "#######", "##.....", "##.....", "##..###", "##..###", "##...##", "##...##", "#######", ".#####."],
  H: ["##...##", "##...##", "##...##", "##...##", "#######", "#######", "##...##", "##...##", "##...##", "##...##"],
  I: ["#######", "#######", "..##...", "..##...", "..##...", "..##...", "..##...", "..##...", "#######", "#######"],
  J: ["...####", "...####", ".....##", ".....##", ".....##", ".....##", "##...##", "##...##", "#######", ".#####."],
  K: ["##...##", "##..##.", "##.##..", "####...", "###....", "####...", "##.##..", "##..##.", "##...##", "##...##"],
  L: ["##.....", "##.....", "##.....", "##.....", "##.....", "##.....", "##.....", "##.....", "#######", "#######"],
  M: ["##...##", "###.###", "##.#.##", "##.#.##", "##...##", "##...##", "##...##", "##...##", "##...##", "##...##"],
  N: ["##...##", "###..##", "###..##", "##.#.##", "##.#.##", "##..###", "##..###", "##...##", "##...##", "##...##"],
  O: [".#####.", "#######", "##...##", "##...##", "##...##", "##...##", "##...##", "##...##", "#######", ".#####."],
  P: ["######.", "#######", "##...##", "##...##", "#######", "######.", "##.....", "##.....", "##.....", "##....."],
  Q: [".#####.", "#######", "##...##", "##...##", "##...##", "##.#.##", "##..##.", "##...##", "#######", ".####.#"],
  R: ["######.", "#######", "##...##", "##...##", "#######", "######.", "##.##..", "##..##.", "##...##", "##...##"],
  S: [".######", "#######", "##.....", "##.....", "######.", "######.", ".....##", ".....##", "#######", "######."],
  T: ["#######", "#######", "...##..", "...##..", "...##..", "...##..", "...##..", "...##..", "...##..", "...##.."],
  U: ["##...##", "##...##", "##...##", "##...##", "##...##", "##...##", "##...##", "##...##", "#######", ".#####."],
  V: ["##...##", "##...##", "##...##", "##...##", "##...##", "##...##", "##...##", "##...##", ".#####.", "..###.."],
  W: ["##...##", "##...##", "##...##", "##...##", "##.#.##", "##.#.##", "##.#.##", "###.###", ".#####.", ".##.##."],
  X: ["##...##", "##...##", ".##.##.", "..###..", "..###..", "..###..", ".##.##.", "##...##", "##...##", "##...##"],
  Y: ["##...##", "##...##", "##...##", ".##.##.", "..###..", "...##..", "...##..", "...##..", "...##..", "...##.."],
  Z: ["#######", "#######", ".....##", "....##.", "...##..", "..##...", ".##....", "##.....", "#######", "#######"],
  "0": [".#####.", "#######", "##...##", "##..###", "##.#.##", "###..##", "##...##", "##...##", "#######", ".#####."],
  "1": ["..##...", ".###...", "####...", "..##...", "..##...", "..##...", "..##...", "..##...", "#######", "#######"],
  "2": [".#####.", "#######", ".....##", ".....##", ".#####.", "#####..", "##.....", "##.....", "#######", "#######"],
  "3": [".#####.", "#######", ".....##", ".....##", "..####.", "..####.", ".....##", ".....##", "#######", ".#####."],
  "4": ["...##..", "..###..", ".#.##..", "##.##..", "##.##..", "#######", "#######", "...##..", "...##..", "...##.."],
  "5": ["#######", "#######", "##.....", "##.....", "######.", ".######", ".....##", ".....##", "#######", "######."],
  "6": [".#####.", "#######", "##.....", "##.....", "######.", "#######", "##...##", "##...##", "#######", ".#####."],
  "7": ["#######", "#######", ".....##", "....##.", "...##..", "..##...", "..##...", "..##...", "..##...", "..##..."],
  "8": [".#####.", "#######", "##...##", "##...##", ".#####.", ".#####.", "##...##", "##...##", "#######", ".#####."],
  "9": [".#####.", "#######", "##...##", "##...##", "#######", ".######", ".....##", ".....##", "#######", ".#####."],
  "!": ["..##...", "..##...", "..##...", "..##...", "..##...", "..##...", ".......", "..##...", "..##...", "......."],
  "?": [".#####.", "#######", "##...##", "....##.", "...##..", "..##...", ".......", "..##...", "..##...", "......."],
  "#": [".##.##.", ".##.##.", "#######", "#######", ".##.##.", ".##.##.", "#######", "#######", ".##.##.", ".##.##."],
  $: ["..##...", ".######", "##.##..", "##.....", ".#####.", ".....##", "..##.##", "######.", "..##...", "..##..."],
  "%": ["##...##", "##..##.", "##.##..", "##.#...", "..##...", "...#.##", "..##.##", ".##..##", "##...##", "##...##"],
  "&": [".##....", "###....", "##.....", ".####..", "##..##.", "##..##.", "##..##.", "##..##.", ".####.#", "..##.##"],
  "*": [".......", "##...##", ".##.##.", "..###..", "#######", "..###..", ".##.##.", "##...##", ".......", "......."],
  "+": [".......", "..##...", "..##...", "..##...", "#######", "#######", "..##...", "..##...", "..##...", "......."],
  "-": [".......", ".......", ".......", ".......", "#######", "#######", ".......", ".......", ".......", "......."],
  "=": [".......", ".......", "#######", "#######", ".......", ".......", "#######", "#######", ".......", "......."],
  "/": [".....##", "....##.", "....##.", "...##..", "...##..", "..##...", "..##...", ".##....", ".##....", "##....."],
  "<": ["....##.", "...##..", "..##...", ".##....", "##.....", "##.....", ".##....", "..##...", "...##..", "....##."],
  ">": [".##....", "..##...", "...##..", "....##.", ".....##", ".....##", "....##.", "...##..", "..##...", ".##...."],
  "(": ["...##..", "..##...", ".##....", "##.....", "##.....", "##.....", "##.....", ".##....", "..##...", "...##.."],
  ")": ["..##...", "...##..", "....##.", ".....##", ".....##", ".....##", ".....##", "....##.", "...##..", "..##..."],
  ".": [".......", ".......", ".......", ".......", ".......", ".......", ".......", "..##...", "..##...", "......."],
  ",": [".......", ".......", ".......", ".......", ".......", ".......", "..##...", "..##...", "...##..", "..##..."],
  ":": [".......", "..##...", "..##...", ".......", ".......", ".......", "..##...", "..##...", ".......", "......."],
  ";": [".......", "..##...", "..##...", ".......", ".......", "..##...", "..##...", "...##..", "..##...", "......."],
  "@": [".#####.", "##...##", "##.###.", "##.#.##", "##.#.##", "##.###.", "##.....", "##...##", ".#####.", "......."],
};

export function glyphOf(ch: string): readonly string[] | null {
  return GLYPHS[ch] ?? null;
}

export function letterGap(cols: number, letters: number): number {
  for (const gap of [2, 1, 0]) {
    const width = letters * 7 + Math.max(0, letters - 1) * gap;
    if (width <= Math.max(1, cols - 2)) return gap;
  }
  return 0;
}

export function truecolorEnabled(colorterm: string | undefined): boolean {
  const value = (colorterm ?? "").toLowerCase();
  return value === "truecolor" || value === "24bit";
}

function mod(tMs: number, cycle: number): number {
  const t = Number.isFinite(tMs) ? Math.floor(tMs) : 0;
  return ((t % cycle) + cycle) % cycle;
}

function poolChar(slot: number, step: number): string | null {
  let x = Math.imul(step + 1, 0x9e3779b1) ^ Math.imul(slot + 1, 0x85ebca6b);
  x = Math.imul(x ^ (x >>> 16), 0x7feb352d);
  x = (x ^ (x >>> 15)) >>> 0;
  for (let i = 0; i < POOL.length; i += 1) {
    const ch = POOL[(x + i) % POOL.length];
    if (ch && GLYPHS[ch]) return ch;
  }
  return null;
}

export function slotsAt(tMs: number, word = WORD): SlotFrame[] {
  const letters = word.toUpperCase();
  const t = mod(tMs, CYCLE_MS);
  const frames: SlotFrame[] = [];
  for (let slot = 0; slot < letters.length; slot += 1) {
    const letter = letters[slot] ?? "";
    const lockAt = SPIN_MS + slot * LOCK_MS;
    if (t < lockAt) {
      frames.push({ ch: poolChar(slot, Math.floor(t / STEP_MS)), shade: "dim" });
      continue;
    }
    const known = Boolean(GLYPHS[letter]);
    const shade: ShadeName = t < lockAt + FLASH_MS ? "flash" : "rest";
    frames.push({ ch: known ? letter : null, shade });
  }
  return frames;
}

function colorOf(shade: ShadeName, truecolor: boolean): CellColor {
  const tone = SHADES[shade];
  return truecolor ? { rgb: tone.rgb } : { cube: tone.cube };
}

type Pixel = { on: boolean; shade: ShadeName | null };

function gridFor(frames: readonly SlotFrame[], gap: number): Pixel[][] {
  const rows: Pixel[][] = Array.from({ length: 10 }, () => []);
  let drawn = 0;
  for (const frame of frames) {
    const glyph = frame.ch ? GLYPHS[frame.ch] : undefined;
    if (!glyph) continue;
    if (drawn > 0) {
      for (const row of rows) {
        for (let g = 0; g < gap; g += 1) row.push({ on: false, shade: null });
      }
    }
    for (let y = 0; y < 10; y += 1) {
      const line = glyph[y] ?? ".......";
      for (const mark of line) rows[y]?.push({ on: mark === "#", shade: frame.shade });
    }
    drawn += 1;
  }
  return rows;
}

const BLANK: WordCell = { ch: " ", color: null };

export function wordmarkLines(
  word = WORD,
  { cols = 100, tMs = SETTLED_MS, truecolor = false, gap }: {
    cols?: number;
    tMs?: number;
    truecolor?: boolean;
    gap?: number;
  } = {},
): { lines: WordCell[][]; gap: number; rows: number } {
  const frames = slotsAt(tMs, word);
  const count = frames.filter((frame) => frame.ch && GLYPHS[frame.ch]).length;
  const usedGap = gap ?? letterGap(cols, Math.max(1, count));
  const grid = gridFor(frames, count > 1 ? usedGap : 0);
  const width = grid[0]?.length ?? 0;
  if (width === 0) {
    return { lines: Array.from({ length: 5 }, () => [{ ...BLANK }]), gap: usedGap, rows: 5 };
  }
  const lines: WordCell[][] = [];
  for (let y = 0; y < 10; y += 2) {
    const cells: WordCell[] = [];
    for (let x = 0; x < width; x += 1) {
      const top = grid[y]?.[x];
      const bot = grid[y + 1]?.[x];
      const topOn = top?.on === true;
      const botOn = bot?.on === true;
      if (!topOn && !botOn) {
        cells.push({ ...BLANK });
        continue;
      }
      let ch = "▄";
      let shade = bot?.shade ?? top?.shade ?? "rest";
      if (topOn && botOn) {
        ch = "█";
        shade = top?.shade ?? shade;
      } else if (topOn) {
        ch = "▀";
        shade = top?.shade ?? shade;
      }
      cells.push({ ch, color: colorOf(shade, truecolor) });
    }
    lines.push(cells);
  }
  return { lines, gap: usedGap, rows: lines.length };
}

export type WordPixel = { x: number; y: number; shade: ShadeName };

export function wordmarkPixels(
  tMs = SETTLED_MS,
  { word = WORD, gap = 1 }: { word?: string; gap?: number } = {},
): { pixels: WordPixel[]; width: number; height: number } {
  const frames = slotsAt(tMs, word);
  const pixels: WordPixel[] = [];
  let cursor = 0;
  let drawn = 0;
  for (const frame of frames) {
    const glyph = frame.ch ? GLYPHS[frame.ch] : undefined;
    if (!glyph) continue;
    if (drawn > 0) cursor += gap;
    for (let y = 0; y < 10; y += 1) {
      const line = glyph[y] ?? "";
      for (let x = 0; x < line.length; x += 1) {
        if (line[x] === "#") pixels.push({ x: cursor + x, y, shade: frame.shade });
      }
    }
    cursor += 7;
    drawn += 1;
  }
  return { pixels, width: Math.max(cursor, 0), height: 10 };
}

export function shadeHex(shade: ShadeName): string {
  const channel = SHADES[shade].rgb.toString(16).padStart(2, "0");
  return `#${channel}${channel}${channel}`;
}

/** One SGR color selector. A cell never carries both 38;5 and 38;2. */
export function cellSgr(cell: WordCell): string {
  if (!cell.color) return "";
  if ("rgb" in cell.color) {
    const n = cell.color.rgb;
    return `38;2;${n};${n};${n}`;
  }
  return `38;5;${cell.color.cube}`;
}
