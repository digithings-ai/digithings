/** Pixel DIGIQUANT lockup. Same cells as the web hero (`QuantWordmark`):
 *  nine glyphs, seven columns each, two columns of gap, ten rows. */

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

/** The hero, packed so it sits in the top-right corner of a terminal row. */
export function markLines(): string[] {
  const lines: string[] = [];
  for (let row = 0; row < MARK_ROWS; row++) {
    let line = "";
    for (let col = 0; col < MARK_COLS; col++) {
      const x = col * 2;
      const y = row * 2;
      let bits = 0;
      if (markFilled(x, y)) bits |= 8;
      if (markFilled(x + 1, y)) bits |= 4;
      if (markFilled(x, y + 1)) bits |= 2;
      if (markFilled(x + 1, y + 1)) bits |= 1;
      line += QUADS[bits] ?? " ";
    }
    lines.push(line);
  }
  return lines;
}
