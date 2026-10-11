// Generator copied verbatim from apps/digiquant-web/app/_chrome/QuantWordmark.tsx
// (#4986, cursor/ui-surfaces-d8c5, with #5416 / DIG-2850: glints and blinking
// strays in their own up/down tone), kept as the parity reference. Imports inlined.
type CSSProperties = Record<string, string | number>;
const columnDelayMs = (col: number) => 250 + col * 16;
// lib/hero-build.ts: sweepDelayMs(1) + BUILD_RISE_MS = columnDelayMs(78) + 360.
const BUILD_DONE_MS = columnDelayMs(9 * 9 - 3) + 360;
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
const WIDTH = 9 * 9 - 2;

function mulberry32(seed: number): () => number {
  let state = seed;
  return () => {
    state = (state + 0x6d2b79f5) | 0;
    let t = Math.imul(state ^ (state >>> 15), 1 | state);
    t = (t + Math.imul(t ^ (t >>> 7), 61 | t)) ^ t;
    return ((t ^ (t >>> 14)) >>> 0) / 4294967296;
  };
}

type Cell = { x: number; y: number; style: CSSProperties };

const tone = (rand: () => number) => (rand() < 0.5 ? "var(--up)" : "var(--down)");

function build(): { letters: Cell[]; strays: Cell[] } {
  const rand = mulberry32(0x9a17);
  const used = new Set<string>();
  const letters: Cell[] = [];
  const glints: Cell[] = [];
  let x = 0;
  for (const ch of WORD) {
    const glyph = GLYPHS[ch];
    for (let y = 0; y < 10; y++) {
      for (let c = 0; c < 7; c++) {
        if (glyph[y][c] !== "#") continue;
        const px = x + c;
        used.add(`${px},${y}`);
        const glint = rand() < 0.045;
        const delay = columnDelayMs(px) + (9 - y) * 9 + Math.floor(rand() * 140);
        const rise = `dq-rise ${260 + Math.floor(rand() * 220)}ms cubic-bezier(0.2,0.7,0.2,1) ${delay}ms backwards`;
        const glintAnim = glint
          ? `dq-glint ${7000 + Math.floor(rand() * 8000)}ms step-end ${3500 + Math.floor(rand() * 6000)}ms infinite`
          : "none";
        const cell: Cell = {
          x: px,
          y,
          style: {
            transformBox: "fill-box",
            transformOrigin: "50% 100%",
            animation: glint ? `${rise}, ${glintAnim}` : rise,
            ["--dq-glint" as string]: glintAnim,
            ["--dq-cell" as string]: tone(rand),
          } as CSSProperties,
        };
        letters.push(cell);
        if (glint) glints.push(cell);
      }
    }
    x += 9;
  }
  mixDirections(letters);
  mixDirections(glints);
  const strays: Cell[] = [];
  const blinks: Cell[] = [];
  while (strays.length < 60) {
    const px = Math.floor(rand() * WIDTH);
    const py = Math.floor(rand() * 10);
    const key = `${px},${py}`;
    if (used.has(key)) continue;
    used.add(key);
    const flicker = `dq-stray ${60 + Math.floor(rand() * 140)}ms linear ${Math.floor(rand() * 1400)}ms backwards`;
    const blink = rand() < 0.35;
    const blinkAnim = `dq-blink ${4000 + Math.floor(rand() * 6000)}ms step-end ${BUILD_DONE_MS + 400 + Math.floor(rand() * 5000)}ms infinite`;
    const cell: Cell = {
      x: px,
      y: py,
      style: {
        opacity: 0,
        animation: blink ? `${flicker}, ${blinkAnim}` : flicker,
        ["--dq-cell" as string]: tone(rand),
      },
    };
    strays.push(cell);
    if (blink) blinks.push(cell);
  }
  mixDirections(strays);
  mixDirections(blinks);
  return { letters, strays };
}

function cellTone(cell: Cell): string {
  return String((cell.style as Record<string, string>)["--dq-cell"] ?? "");
}

/** The rise has to show both sides of the pair, not a run of one color. */
function mixDirections(cells: Cell[]) {
  if (cells.length < 2) return;
  if (!cells.some((cell) => cellTone(cell) === "var(--up)")) {
    (cells[0].style as Record<string, string>)["--dq-cell"] = "var(--up)";
  }
  if (!cells.some((cell) => cellTone(cell) === "var(--down)")) {
    (cells[1].style as Record<string, string>)["--dq-cell"] = "var(--down)";
  }
}


export const LEGACY_DIGIQUANT = build();
