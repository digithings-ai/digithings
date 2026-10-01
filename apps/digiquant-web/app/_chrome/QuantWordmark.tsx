import type { CSSProperties } from "react";
import { BUILD_COLUMNS, BUILD_WORD, columnDelayMs } from "@/lib/hero-build";

/** Pixel lockup for the hero: DIGIQUANT drawn in square cells that grow up from
 *  the baseline, left to right, like bars of a bar chart building the word.
 *  A few cells glint in the accent afterwards and strays flicker once. No CSS
 *  classes: animations are inline, keyframes live in globals.css, and
 *  [data-dq-anim] switches them off under reduced motion. */

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

const WORD = BUILD_WORD;
const WIDTH = BUILD_COLUMNS;

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

function build(): { letters: Cell[]; strays: Cell[] } {
  const rand = mulberry32(0x9a17);
  const used = new Set<string>();
  const letters: Cell[] = [];
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
        letters.push({
          x: px,
          y,
          style: {
            transformBox: "fill-box",
            transformOrigin: "50% 100%",
            animation: glint
              ? `${rise}, dq-glint ${7000 + Math.floor(rand() * 8000)}ms step-end ${3500 + Math.floor(rand() * 6000)}ms infinite`
              : rise,
          },
        });
      }
    }
    x += 9;
  }
  const strays: Cell[] = [];
  while (strays.length < 60) {
    const px = Math.floor(rand() * WIDTH);
    const py = Math.floor(rand() * 10);
    const key = `${px},${py}`;
    if (used.has(key)) continue;
    used.add(key);
    strays.push({
      x: px,
      y: py,
      style: { opacity: 0, animation: `dq-stray ${60 + Math.floor(rand() * 140)}ms linear ${Math.floor(rand() * 1400)}ms backwards` },
    });
  }
  return { letters, strays };
}

const CELLS = build();

/** `idle` holds every cell back (opacity 0, no animation) until it flips to `run`, which
 *  plays the build. The footer copy uses it to build when it first scrolls into view. */
export function QuantWordmark({ className, phase = "run" }: { className?: string; phase?: "run" | "idle" }) {
  const idle = phase === "idle";
  return (
    <svg
      xmlns="http://www.w3.org/2000/svg"
      viewBox={`0 0 ${WIDTH} 10`}
      role="img"
      aria-label="digiquant"
      shapeRendering="crispEdges"
      className={className}
    >
      {CELLS.letters.map((cell) => (
        <rect
          key={`c${cell.x}-${cell.y}`}
          x={cell.x}
          y={cell.y}
          width="1"
          height="1"
          data-dq-anim=""
          style={idle ? { opacity: 0 } : cell.style}
        />
      ))}
      {CELLS.strays.map((cell) => (
        <rect
          key={`n${cell.x}-${cell.y}`}
          x={cell.x}
          y={cell.y}
          width="1"
          height="1"
          data-dq-anim=""
          style={idle ? { opacity: 0 } : cell.style}
        />
      ))}
    </svg>
  );
}
