/** Pixel DIGIQUANT lockup. Same cells as the web hero (`QuantWordmark`):
 *  nine glyphs, seven columns each, two columns of gap, ten rows.
 *  The desk header packs eight of those rows into two braille rows so the
 *  mark sits with the web bar (`h-[14px]` inside `h-8`), on the left.
 *  The columns fill once per process, then one cell glints. */

const GLYPHS: Record<string, string[]> = {
  D: ["######.", "#######", "##...##", "##...##", "##...##", "##...##", "##...##", "##...##", "#######", "######."],
  I: ["#######", "#######", "..##...", "..##...", "..##...", "..##...", "..##...", "..##...", "#######", "#######"],
  G: [".#####.", "#######", "##.....", "##.....", "##..###", "##..###", "##...##", "##...##", "#######", ".#####."],
  Q: [".#####.", "#######", "##...##", "##...##", "##...##", "##.#.##", "##..###", "##..###", "#######", ".######"],
  U: ["##...##", "##...##", "##...##", "##...##", "##...##", "##...##", "##...##", "##...##", "#######", ".#####."],
  A: [".#####.", "#######", "##...##", "##...##", "#######", "#######", "##...##", "##...##", "##...##", "##...##"],
  N: ["##...##", "###..##", "###..##", "##.#.##", "##.#.##", "##..###", "##..###", "##...##", "##...##", "##...##"],
  T: ["#######", "#######", "...##..", "...##..", "...##..", "...##..", "...##..", "...##..", "...##..", "...##.."],
};

export const MARK_GLYPHS = GLYPHS;
export const MARK_WORD = "DIGIQUANT";
export const MARK_PIXEL_W = MARK_WORD.length * 9 - 2;
export const MARK_PIXEL_H = 10;
/** Source rows kept in the header. Four samples per braille row. */
export const MARK_SAMPLE_Y = [0, 1, 3, 4, 5, 6, 8, 9] as const;
export const MARK_COLS = Math.ceil(MARK_PIXEL_W / 2);
export const MARK_ROWS = MARK_SAMPLE_Y.length / 4;
/** One left-to-right pass, about as long as the web rise. */
export const REVEAL_MS = 1860;
export const GLINT_EVERY_MS = 6400;
export const GLINT_MS = 160;

/** Braille dots, two source columns by four sampled rows. Blank stays a space. */
const BRAILLE_DOTS = [
  [0x01, 0x08],
  [0x02, 0x10],
  [0x04, 0x20],
  [0x40, 0x80],
] as const;

export function markFilled(x: number, y: number): boolean {
  if (x < 0 || y < 0 || x >= MARK_PIXEL_W || y >= MARK_PIXEL_H) return false;
  let cursor = 0;
  for (const ch of MARK_WORD) {
    const glyph = GLYPHS[ch];
    if (!glyph) return false;
    if (x >= cursor && x < cursor + 7) return glyph[y]?.[x - cursor] === "#";
    cursor += 9;
  }
  return false;
}

/** The header mark. `limit` is how many pixel columns have filled. */
export function markLines(limit = MARK_PIXEL_W): string[] {
  const cap = Math.max(0, Math.min(MARK_PIXEL_W, Math.floor(limit)));
  const lines: string[] = [];
  for (let row = 0; row < MARK_ROWS; row++) {
    let line = "";
    for (let col = 0; col < MARK_COLS; col++) {
      const x = col * 2;
      let bits = 0;
      for (let i = 0; i < BRAILLE_DOTS.length; i++) {
        const y = MARK_SAMPLE_Y[row * 4 + i] ?? -1;
        const dot = BRAILLE_DOTS[i] ?? [0, 0];
        if (x < cap && markFilled(x, y)) bits |= dot[0];
        if (x + 1 < cap && markFilled(x + 1, y)) bits |= dot[1];
      }
      line += bits === 0 ? " " : String.fromCharCode(0x2800 + bits);
    }
    lines.push(line);
  }
  return lines;
}

export function revealedColumns(elapsedMs: number): number {
  if (!Number.isFinite(elapsedMs) || elapsedMs <= 0) return 0;
  if (elapsedMs >= REVEAL_MS) return MARK_PIXEL_W;
  return Math.floor((elapsedMs / REVEAL_MS) * MARK_PIXEL_W);
}

let originMs: number | null = null;

export function resetMarkClock(): void {
  originMs = null;
}

/** Elapsed time since this process first drew the mark. */
export function markElapsed(now: number): number {
  if (originMs === null) originMs = now;
  return Math.max(0, now - originMs);
}

let ink: { row: number; col: number }[] | null = null;

function inkCells(): { row: number; col: number }[] {
  if (ink) return ink;
  ink = [];
  const lines = markLines();
  for (let row = 0; row < lines.length; row++) {
    const line = lines[row] ?? "";
    for (let col = 0; col < line.length; col++) {
      if (line[col] !== " ") ink.push({ row, col });
    }
  }
  return ink;
}

/** Stable up/down for one header cell during the reveal. Both sides occur. */
export function markDirection(row: number, col: number): "up" | "down" {
  let n = Math.imul(row + 1, 0x9e3779b1) ^ Math.imul(col + 1, 0x85ebca6b);
  n = Math.imul(n ^ (n >>> 13), 0xc2b2ae35);
  return (n >>> 0) % 2 === 0 ? "up" : "down";
}

/** One non-space cell, after the reveal. Null while the word is still filling. */
export function glintCell(elapsedMs: number): { row: number; col: number } | null {
  if (elapsedMs < REVEAL_MS) return null;
  const idle = elapsedMs - REVEAL_MS;
  const span = GLINT_EVERY_MS + GLINT_MS;
  if (idle % span < GLINT_EVERY_MS) return null;
  const cells = inkCells();
  if (cells.length === 0) return null;
  return cells[Math.floor(idle / span) % cells.length] ?? null;
}
