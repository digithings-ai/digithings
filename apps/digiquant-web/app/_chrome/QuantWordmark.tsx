"use client";

import { useEffect, useRef, type CSSProperties } from "react";
import { BUILD_COLUMNS, BUILD_DONE_MS, BUILD_WORD, columnDelayMs } from "@/lib/hero-build";
import { HERO_PLAYED_KEY, nextHeroLive, type HeroGateView } from "@/lib/hero-play";

/** Pixel lockup for the hero: DIGIQUANT drawn in square cells that grow up from
 *  the baseline, left to right, like bars of a bar chart building the word.
 *  The rise mixes digiquant up and down so the word reads as price moving
 *  both ways, then settles to ink. Afterwards a fifth of the cells keep
 *  flashing and most strays keep blinking, each in its own up or down tone, so
 *  red and green both stay on the word. The hero (`replay`) builds on every load; other marks build
 *  once per tab and later loads keep only the glint. No CSS
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

/** Share of letter cells that keep flashing up or down after the build. Enough
 *  that red and green both stay on the word at any moment, not a rare glint. */
const GLINT_SHARE = 0.2;

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
        const glint = rand() < GLINT_SHARE;
        const delay = columnDelayMs(px) + (9 - y) * 9 + Math.floor(rand() * 140);
        const rise = `dq-rise ${260 + Math.floor(rand() * 220)}ms cubic-bezier(0.2,0.7,0.2,1) ${delay}ms backwards`;
        const glintAnim = glint
          ? `dq-glint ${1400 + Math.floor(rand() * 2600)}ms step-end ${BUILD_DONE_MS + Math.floor(rand() * 1600)}ms infinite`
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
    const blink = rand() < 0.6;
    const blinkAnim = `dq-blink ${1800 + Math.floor(rand() * 3200)}ms step-end ${BUILD_DONE_MS + Math.floor(rand() * 2000)}ms infinite`;
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

/** Each set (rise, glint, blink) has to show both sides of the pair, not a run of one color. */
function mixDirections(cells: Cell[]) {
  if (cells.length < 2) return;
  if (!cells.some((cell) => cellTone(cell) === "var(--up)")) {
    (cells[0].style as Record<string, string>)["--dq-cell"] = "var(--up)";
  }
  if (!cells.some((cell) => cellTone(cell) === "var(--down)")) {
    (cells[1].style as Record<string, string>)["--dq-cell"] = "var(--down)";
  }
}

const CELLS = build();

type LiveGate = { started: number; node: SVGSVGElement | null };

const GATE_HOST = "__dqHeroGate";

function readGate(): LiveGate | null {
  return (window as unknown as Record<string, LiveGate | undefined>)[GATE_HOST] ?? null;
}

function writeGate(gate: LiveGate) {
  (window as unknown as Record<string, LiveGate>)[GATE_HOST] = gate;
}

function gateView(gate: LiveGate | null): HeroGateView | null {
  if (!gate) return null;
  return { started: gate.started, connected: gate.node?.isConnected === true };
}

/** `idle` holds every cell back (opacity 0, no animation) until it flips to `run`.
 *  The rise plays once per tab. Later mounts keep the glint only.
 *  `replay` marks (the top hero, the top bar, the closing mark) build on every
 *  load whether or not the tab has played.
 *  `armed` stays false until a scroll-triggered mark is allowed to claim. */
export function QuantWordmark({
  className,
  phase = "run",
  armed = true,
  replay = false,
}: {
  className?: string;
  phase?: "run" | "idle";
  armed?: boolean;
  replay?: boolean;
}) {
  const idle = phase === "idle";
  const ref = useRef<SVGSVGElement>(null);

  useEffect(() => {
    const root = document.documentElement;
    const gate = readGate();
    const decision = nextHeroLive({
      played: root.getAttribute("data-dq-hero") === "played",
      replay,
      armed,
      idle,
      now: performance.now(),
      gate: gateView(gate),
    });
    if (!decision.live) return;
    const node = ref.current;
    const started = decision.claim ? performance.now() : (gate?.started ?? performance.now());
    writeGate({ started, node });
    // Imperative: React must not own this attribute, or the rise is cut off
    // when the tab is marked played. A later render leaves it in place.
    node?.setAttribute("data-dq-live", "");
    if (!decision.claim) return;
    try {
      if (window.sessionStorage.getItem(HERO_PLAYED_KEY) !== "1") {
        window.sessionStorage.setItem(HERO_PLAYED_KEY, "1");
      }
    } catch {
      /* private mode: this document still plays once */
    }
    root.setAttribute("data-dq-hero", "played");
  }, [armed, idle, replay]);

  return (
    <svg
      ref={ref}
      xmlns="http://www.w3.org/2000/svg"
      viewBox={`0 0 ${WIDTH} 10`}
      role="img"
      aria-label="digiquant"
      shapeRendering="crispEdges"
      className={className}
      // The hero owns the attribute from the first paint, so the played-tab
      // CSS never cuts its rise. Other marks get it from the effect.
      data-dq-live={replay && !idle ? "" : undefined}
    >
      {CELLS.letters.map((cell) => (
        <rect
          key={`c${cell.x}-${cell.y}`}
          x={cell.x}
          y={cell.y}
          width="1"
          height="1"
          data-dq-anim={idle ? undefined : ""}
          data-dq-build={idle ? undefined : ""}
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
          data-dq-anim={idle ? undefined : ""}
          data-dq-stray={idle ? undefined : ""}
          style={idle ? { opacity: 0 } : cell.style}
        />
      ))}
    </svg>
  );
}
