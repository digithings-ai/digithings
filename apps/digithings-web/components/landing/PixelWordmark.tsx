import type { CSSProperties } from "react";

const GLYPHS: Record<string, string[]> = {
  D: ["######.", "#######", "##...##", "##...##", "##...##", "##...##", "##...##", "##...##", "#######", "######."],
  I: ["#######", "#######", "..##...", "..##...", "..##...", "..##...", "..##...", "..##...", "#######", "#######"],
  G: [".#####.", "#######", "##.....", "##.....", "##..###", "##..###", "##...##", "##...##", "#######", ".#####."],
  T: ["#######", "#######", "...##..", "...##..", "...##..", "...##..", "...##..", "...##..", "...##..", "...##.."],
  H: ["##...##", "##...##", "##...##", "##...##", "#######", "#######", "##...##", "##...##", "##...##", "##...##"],
  N: ["##...##", "###..##", "###..##", "##.#.##", "##.#.##", "##..###", "##..###", "##...##", "##...##", "##...##"],
  S: [".######", "#######", "##.....", "##.....", "######.", "######.", ".....##", ".....##", "#######", "######."],
};

const STEPS = [0.36, 0.5, 0.66, 0.82, 1];

function css(vars: Record<string, string | number>): CSSProperties {
  return vars as CSSProperties;
}

function mulberry32(seed: number): () => number {
  let state = seed;
  return () => {
    state = (state + 0x6d2b79f5) | 0;
    let t = Math.imul(state ^ (state >>> 15), 1 | state);
    t = (t + Math.imul(t ^ (t >>> 7), 61 | t)) ^ t;
    return ((t ^ (t >>> 14)) >>> 0) / 4294967296;
  };
}

type Cell = { x: number; y: number; glint: boolean; style: CSSProperties };

function wordCells(): { letters: Cell[]; stray: Cell[] } {
  const rand = mulberry32(0xd161);
  const pick = () => STEPS[Math.floor(rand() * STEPS.length)] ?? 1;
  const used = new Set<string>();
  const letters: Cell[] = [];
  let x = 0;
  for (const ch of "DIGITHINGS") {
    const glyph = GLYPHS[ch];
    if (!glyph) continue;
    for (let y = 0; y < 10; y++) {
      const row = glyph[y] ?? "";
      for (let c = 0; c < 7; c++) {
        if (row[c] !== "#") continue;
        const px = x + c;
        letters.push({ x: px, y, glint: false, style: {} });
        used.add(`${px},${y}`);
      }
    }
    x += 9;
  }
  const glint = new Set<number>();
  while (glint.size < 13) glint.add(Math.floor(rand() * letters.length));
  letters.forEach((cell, index) => {
    cell.glint = glint.has(index);
    cell.style = css({
      "--d": `${(rand() * 692 + 8) | 0}ms`,
      "--t": `${(rand() * 380 + 240) | 0}ms`,
      "--a": pick(),
      "--b": pick(),
      "--c": pick(),
      "--f": pick(),
      ...(cell.glint
        ? { "--g": `${(rand() * 6500 + 2500) | 0}ms`, "--gp": `${(rand() * 8000 + 7000) | 0}ms` }
        : {}),
    });
  });
  const stray: Cell[] = [];
  while (stray.length < 70) {
    const px = Math.floor(rand() * 88);
    const py = Math.floor(rand() * 10);
    const key = `${px},${py}`;
    if (used.has(key)) continue;
    used.add(key);
    stray.push({
      x: px,
      y: py,
      glint: false,
      style: css({ "--d": `${(rand() * 1100) | 0}ms`, "--t": `${(rand() * 140 + 60) | 0}ms` }),
    });
  }
  return { letters, stray };
}

const WORD = wordCells();

/** Pixel lockup. Cells build in, a few glint in the accent, and strays flicker once. */
export function PixelWordmark() {
  return (
    <svg
      className="pixel-word"
      xmlns="http://www.w3.org/2000/svg"
      viewBox="0 0 88 10"
      fill="currentColor"
      role="img"
      aria-label="digithings"
    >
      {WORD.letters.map((cell) => (
        <rect
          key={`c${cell.x}-${cell.y}`}
          x={cell.x}
          y={cell.y}
          width="1"
          height="1"
          className={cell.glint ? "c g" : "c"}
          style={cell.style}
        />
      ))}
      {WORD.stray.map((cell) => (
        <rect
          key={`n${cell.x}-${cell.y}`}
          x={cell.x}
          y={cell.y}
          width="1"
          height="1"
          className="n"
          style={cell.style}
        />
      ))}
    </svg>
  );
}
