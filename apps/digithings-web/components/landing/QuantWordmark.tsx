/**
 * The digiquant pixel wordmark, as digiquant.io draws it: DIGIQUANT in square cells,
 * ten rows tall. Glyphs are copied from `apps/digiquant-web/app/_chrome/QuantWordmark.tsx`
 * so the two sites share one mark; this copy is the finished, static state (no build
 * animation, no strays) and takes its colour from `currentColor`.
 */

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

const WORD = "DIGIQUANT";
const GLYPH_WIDTH = 7;
const GLYPH_GAP = 2;
const WIDTH = WORD.length * (GLYPH_WIDTH + GLYPH_GAP) - GLYPH_GAP;

function cells(): { x: number; y: number }[] {
  const out: { x: number; y: number }[] = [];
  let offset = 0;
  for (const ch of WORD) {
    const glyph = GLYPHS[ch];
    if (glyph) {
      glyph.forEach((row, y) => {
        for (let c = 0; c < GLYPH_WIDTH; c += 1) {
          if (row[c] === "#") out.push({ x: offset + c, y });
        }
      });
    }
    offset += GLYPH_WIDTH + GLYPH_GAP;
  }
  return out;
}

const CELLS = cells();

export function QuantWordmark({ className }: { className?: string }) {
  return (
    <svg
      xmlns="http://www.w3.org/2000/svg"
      viewBox={`0 0 ${WIDTH} 10`}
      role="img"
      aria-label="digiquant"
      shapeRendering="crispEdges"
      fill="currentColor"
      className={className}
    >
      {CELLS.map((cell) => (
        <rect key={`${cell.x}-${cell.y}`} x={cell.x} y={cell.y} width="1" height="1" />
      ))}
    </svg>
  );
}
