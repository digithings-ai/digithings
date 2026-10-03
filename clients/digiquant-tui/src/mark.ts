/** Pixel DIGIQUANT lockup. Same cells as the web hero (`QuantWordmark`):
 *  nine glyphs, seven columns each, two columns of gap, ten rows.
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
export const MARK_COLS = Math.ceil(MARK_PIXEL_W / 2);
export const MARK_ROWS = Math.ceil(MARK_PIXEL_H / 2);
/** One left-to-right pass, about as long as the web rise. */
export const REVEAL_MS = 1860;
export const GLINT_EVERY_MS = 6400;
export const GLINT_MS = 160;

/** Quadrant cells, index = UL<<3 | UR<<2 | LL<<1 | LR. Two pixel rows per cell. */
const QUADS = [
  " ", "▗", "▖", "▄",
  "▝", "▐", "▞", "▟",
  "▘", "▚", "▌", "▙",
  "▀", "▜", "▛", "█",
];

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

/** The hero, packed so it sits in the top-right corner of a terminal row.
 *  `limit` is how many pixel columns have filled. The default is the whole word. */
export function markLines(limit = MARK_PIXEL_W): string[] {
  const cap = Math.max(0, Math.min(MARK_PIXEL_W, Math.floor(limit)));
  const lines: string[] = [];
  for (let row = 0; row < MARK_ROWS; row++) {
    let line = "";
    for (let col = 0; col < MARK_COLS; col++) {
      const x = col * 2;
      const y = row * 2;
      let bits = 0;
      if (x < cap && markFilled(x, y)) bits |= 8;
      if (x + 1 < cap && markFilled(x + 1, y)) bits |= 4;
      if (x < cap && markFilled(x, y + 1)) bits |= 2;
      if (x + 1 < cap && markFilled(x + 1, y + 1)) bits |= 1;
      line += QUADS[bits] ?? " ";
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
