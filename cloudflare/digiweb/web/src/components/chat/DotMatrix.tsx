"use client";

import { useEffect, useState, type ComponentProps } from "react";

/**
 * 5×5 snap-on/off cube matrix. Motion states are agent actions; static
 * states are status and chrome glyphs. Unlit cells are omitted — only lit
 * cubes paint. No opacity ease — cubes are on or off.
 */

const GRID = 5;
const CENTER = (GRID - 1) / 2;
const CELL_COUNT = GRID * GRID;
const STEP_MS = 120;

const idx = (row: number, col: number) => row * GRID + col;

const chebyshev = (i: number) => {
  const row = Math.floor(i / GRID);
  const col = i % GRID;
  return Math.max(Math.abs(row - CENTER), Math.abs(col - CENTER));
};

const cellsAt = (distance: number) => {
  const lit: number[] = [];
  for (let i = 0; i < CELL_COUNT; i += 1) {
    if (chebyshev(i) === distance) lit.push(i);
  }
  return lit;
};

const cellsAtMost = (distance: number) => {
  const lit: number[] = [];
  for (let i = 0; i < CELL_COUNT; i += 1) {
    if (chebyshev(i) <= distance) lit.push(i);
  }
  return lit;
};

const rowCells = (row: number) => {
  const lit: number[] = [];
  for (let col = 0; col < GRID; col += 1) lit.push(idx(row, col));
  return lit;
};

const colCells = (col: number) => {
  const lit: number[] = [];
  for (let row = 0; row < GRID; row += 1) lit.push(idx(row, col));
  return lit;
};

/** Clockwise rim, starting top-left. */
const PERIMETER = [
  idx(0, 0),
  idx(0, 1),
  idx(0, 2),
  idx(0, 3),
  idx(0, 4),
  idx(1, 4),
  idx(2, 4),
  idx(3, 4),
  idx(4, 4),
  idx(4, 3),
  idx(4, 2),
  idx(4, 1),
  idx(4, 0),
  idx(3, 0),
  idx(2, 0),
  idx(1, 0),
];

const unionRows = (...rows: number[]) => rows.flatMap(rowCells);

const glyph = (dots: readonly (readonly [number, number])[]) =>
  dots.map(([row, col]) => idx(row, col));

const CHECK = glyph([
  [1, 4],
  [2, 3],
  [3, 0],
  [3, 2],
  [4, 1],
]);
const CROSS = glyph([
  [0, 0],
  [0, 4],
  [1, 1],
  [1, 3],
  [2, 2],
  [3, 1],
  [3, 3],
  [4, 0],
  [4, 4],
]);
const BANG = glyph([
  [0, 2],
  [1, 2],
  [2, 2],
  [4, 2],
]);
const CORNERS = [idx(0, 0), idx(0, 4), idx(4, 0), idx(4, 4)];
/** Lit plus of cubes — attach / add. */
const PLUS = glyph([
  [0, 2],
  [1, 2],
  [2, 0],
  [2, 1],
  [2, 2],
  [2, 3],
  [2, 4],
  [3, 2],
  [4, 2],
]);
/** Inverse plus — 2×2 in each corner; empty mid row/col is the plus. */
const NEW_CHAT = glyph([
  [0, 0],
  [0, 1],
  [0, 3],
  [0, 4],
  [1, 0],
  [1, 1],
  [1, 3],
  [1, 4],
  [3, 0],
  [3, 1],
  [3, 3],
  [3, 4],
  [4, 0],
  [4, 1],
  [4, 3],
  [4, 4],
]);
/** Small centered `^` — status `up` only. */
const ARROW_UP = glyph([
  [1, 2],
  [2, 1],
  [2, 3],
]);
/** Small centered `v` — status `down` only. */
const ARROW_DOWN = glyph([
  [2, 1],
  [2, 3],
  [3, 2],
]);
/** Small `>` centered so a 90° rotate around the grid becomes `down`. */
const ARROW_RIGHT = glyph([
  [1, 2],
  [2, 3],
  [3, 2],
]);
/** Small `<` — exact mirror of the user `>`. */
const ARROW_LEFT = glyph([
  [1, 3],
  [2, 2],
  [3, 3],
]);
/** Download: down arrow into a 5-wide tray. */
const TRAY_DOWNLOAD = glyph([
  [0, 2],
  [1, 2],
  [2, 1],
  [2, 2],
  [2, 3],
  [3, 2],
  [4, 0],
  [4, 1],
  [4, 2],
  [4, 3],
  [4, 4],
]);
/** Export: up arrow out of the same bottom tray. */
const TRAY_EXPORT = glyph([
  [0, 2],
  [1, 1],
  [1, 2],
  [1, 3],
  [2, 2],
  [3, 2],
  [4, 0],
  [4, 1],
  [4, 2],
  [4, 3],
  [4, 4],
]);
/** Double `v` — scroll to bottom, not download and not `down`. */
const SCROLL_CHEVRONS = glyph([
  [1, 1],
  [1, 3],
  [2, 2],
  [3, 1],
  [3, 3],
  [4, 2],
]);
/** Centered 3×3 stop block. */
const STOP_SQUARE = glyph([
  [1, 1],
  [1, 2],
  [1, 3],
  [2, 1],
  [2, 2],
  [2, 3],
  [3, 1],
  [3, 2],
  [3, 3],
]);
/** Corner brackets — system, not a stop square. */
const SYSTEM_BRACKETS = glyph([
  [0, 0],
  [0, 1],
  [0, 3],
  [0, 4],
  [1, 0],
  [1, 4],
  [3, 0],
  [3, 4],
  [4, 0],
  [4, 1],
  [4, 3],
  [4, 4],
]);
/** Compact open `>` — two cubes per arm including the tip. */
const USER_CHEVRON = glyph([
  [1, 1],
  [2, 2],
  [3, 1],
]);
/** Compact filled `▸` — two cubes per side. */
const ASSISTANT_CHEVRON = glyph([
  [1, 0],
  [1, 1],
  [2, 0],
  [2, 1],
  [2, 2],
  [3, 0],
  [3, 1],
]);
/** Four cubes in a diamond — example prompts. */
const EXAMPLE_DIAMOND = glyph([
  [1, 2],
  [2, 1],
  [2, 3],
  [3, 2],
]);
/**
 * Like / dislike: 2×2 thumb on the *left* of an outlined fist.
 * A centered thumb reads as a chimney; left-aligned is the usual like icon.
 *
 *   ■ ■ · · ·        ■ ■ ■ ■ ■
 *   ■ ■ · · ·        ■ · · · ■
 *   ■ ■ ■ ■ ■        ■ ■ ■ ■ ■
 *   ■ · · · ■        ■ ■ · · ·
 *   ■ ■ ■ ■ ■        ■ ■ · · ·
 */
const THUMB_UP = glyph([
  [0, 0],
  [0, 1],
  [1, 0],
  [1, 1],
  [2, 0],
  [2, 1],
  [2, 2],
  [2, 3],
  [2, 4],
  [3, 0],
  [3, 4],
  [4, 0],
  [4, 1],
  [4, 2],
  [4, 3],
  [4, 4],
]);
const THUMB_DOWN = glyph([
  [0, 0],
  [0, 1],
  [0, 2],
  [0, 3],
  [0, 4],
  [1, 0],
  [1, 4],
  [2, 0],
  [2, 1],
  [2, 2],
  [2, 3],
  [2, 4],
  [3, 0],
  [3, 1],
  [4, 0],
  [4, 1],
]);

const hold = (distances: number[]) => distances.map((d) => cellsAt(d));
const fill = (distances: number[]) => distances.map((d) => cellsAtMost(d));
/** Consecutive cells on a ring — a thick spinning arc, not one cube. */
const trail = (ring: readonly number[], length: number) =>
  ring.map((_, start) =>
    Array.from({ length }, (_, i) => ring[(start + i) % ring.length]),
  );

const PATTERNS = {
  idle: [CORNERS],
  /** Outer rim sweep — a moving C, as dense as thinking's outer ring. */
  loading: trail(PERIMETER, 9),
  /** Hollow ring in, hold center, ring out. */
  thinking: hold([2, 2, 1, 1, 0, 0, 1, 1, 2, 2]),
  /**
   * Press: two bars close on the middle, hold the work, then open.
   * Not another spinner — tool execution is a stamp, not a wait.
   */
  tool: [
    unionRows(0, 4),
    unionRows(0, 4),
    unionRows(1, 3),
    unionRows(1, 3),
    unionRows(1, 2, 3),
    unionRows(1, 2, 3),
    unionRows(1, 3),
    unionRows(1, 3),
  ],
  /** Scanline down the rows. */
  executing: [0, 1, 2, 3, 4].map(rowCells),
  /** Scanline across the columns (web search). */
  searching: [0, 1, 2, 3, 4].map(colCells),
  /** Filled square shrinks to the center, then grows back. */
  compacting: fill([2, 2, 1, 1, 0, 0, 1, 1, 2, 2]),
  warning: [BANG],
  error: [CROSS],
  success: [CHECK],
  /**
   * Light bulb — reasoning done. Not a check (that's tools) and not a ring
   * (that's thinking in motion).
   *
   *   · ■ ■ ■ ·
   *   ■ ■ ■ ■ ■
   *   ■ ■ ■ ■ ■
   *   · · ■ · ·
   *   · ■ ■ ■ ·
   */
  thought: [
    glyph([
      [0, 1],
      [0, 2],
      [0, 3],
      [1, 0],
      [1, 1],
      [1, 2],
      [1, 3],
      [1, 4],
      [2, 0],
      [2, 1],
      [2, 2],
      [2, 3],
      [2, 4],
      [3, 2],
      [4, 1],
      [4, 2],
      [4, 3],
    ]),
  ],
  /** Two overlapping page squares. */
  copy: [
    glyph([
      [0, 2],
      [0, 3],
      [0, 4],
      [1, 2],
      [1, 4],
      [2, 0],
      [2, 1],
      [2, 2],
      [2, 3],
      [2, 4],
      [3, 0],
      [3, 2],
      [4, 0],
      [4, 1],
      [4, 2],
    ]),
  ],
  /** I-beam / text caret. */
  edit: [
    glyph([
      [0, 0],
      [0, 1],
      [0, 2],
      [0, 3],
      [0, 4],
      [1, 2],
      [2, 2],
      [3, 2],
      [4, 0],
      [4, 1],
      [4, 2],
      [4, 3],
      [4, 4],
    ]),
  ],
  /** Lit plus of cubes — composer attach only. */
  attach: [PLUS],
  /** Enter/send: top-right bend, right stem, bar, left `<` arrowhead. */
  send: [
    glyph([
      [0, 2],
      [0, 3],
      [0, 4],
      [1, 4],
      [2, 1],
      [2, 4],
      [3, 0],
      [3, 1],
      [3, 2],
      [3, 3],
      [3, 4],
      [4, 1],
    ]),
  ],
  /** Three cubes on the mid row. */
  more: [glyph([[2, 0], [2, 2], [2, 4]])],
  /** Cycle: down the right with a head; up the left with a head. */
  refresh: [
    glyph([
      [0, 1],
      [0, 2],
      [0, 3],
      [0, 4],
      [1, 0],
      [1, 4],
      [2, 0],
      [2, 1],
      [2, 3],
      [2, 4],
      [3, 0],
      [3, 4],
      [4, 0],
      [4, 1],
      [4, 2],
      [4, 3],
    ]),
  ],
  /** Up arrow out of a bottom tray. */
  export: [TRAY_EXPORT],
  /** Down arrow into a bottom tray. */
  download: [TRAY_DOWNLOAD],
  /** Centered 3×3 block — a stop, not a single cell. */
  stop: [STOP_SQUARE],
  /** Clear × without the error center fill. */
  remove: [
    glyph([
      [0, 0],
      [0, 4],
      [1, 1],
      [1, 3],
      [3, 1],
      [3, 3],
      [4, 0],
      [4, 4],
    ]),
  ],
  /** Double chevron down — scroll to bottom. */
  scroll: [SCROLL_CHEVRONS],
  /** Tiny centered `^`. */
  up: [ARROW_UP],
  /** Tiny centered `v`. */
  down: [ARROW_DOWN],
  /** Small `<` — mirror of `next` / `user`. */
  prev: [ARROW_LEFT],
  /** Small `>` — same size as the user arrow. */
  next: [USER_CHEVRON],
  /** Mic. */
  dictate: [
    glyph([
      [0, 1],
      [0, 2],
      [0, 3],
      [1, 1],
      [1, 3],
      [2, 1],
      [2, 2],
      [2, 3],
      [3, 2],
      [4, 0],
      [4, 1],
      [4, 2],
      [4, 3],
      [4, 4],
    ]),
  ],
  /** Inverse plus — 2×2 corners; new chat, not attach. */
  newChat: [NEW_CHAT],
  /** Thumb pad + fist. */
  thumbsUp: [THUMB_UP],
  /** Vertical mirror of thumbsUp. */
  thumbsDown: [THUMB_DOWN],
  /** Disclosure `>` — rotate 90° in a square to point down. Not the fat V. */
  expand: [ARROW_RIGHT],
  /** User role — compact open `>`. */
  user: [USER_CHEVRON],
  /** Assistant role — compact filled `▸`. */
  assistant: [ASSISTANT_CHEVRON],
  /** Example prompt — outline diamond. */
  example: [EXAMPLE_DIAMOND],
  /** System aside — corner brackets. */
  system: [SYSTEM_BRACKETS],
} as const;

export type DotMatrixState = keyof typeof PATTERNS;

const dotMatrixStates = Object.keys(PATTERNS) as readonly DotMatrixState[];

export type DotMatrixProps = Omit<ComponentProps<"span">, "children"> & {
  state?: DotMatrixState;
  label?: string;
};

function cx(...parts: Array<string | false | null | undefined>): string {
  return parts.filter(Boolean).join(" ");
}

function DotMatrix({
  className,
  state = "loading",
  label,
  ...props
}: DotMatrixProps) {
  const frames = PATTERNS[state];
  const [frame, setFrame] = useState(0);

  useEffect(() => {
    setFrame(0);
    if (frames.length <= 1) return;
    const mq = window.matchMedia("(prefers-reduced-motion: reduce)");
    if (mq.matches) return;
    const id = window.setInterval(() => {
      setFrame((current) => (current + 1) % frames.length);
    }, STEP_MS);
    return () => window.clearInterval(id);
  }, [frames]);

  const lit = new Set(frames[frame] ?? frames[0]);

  return (
    <span
      {...props}
      data-slot="dot-matrix"
      data-state={state}
      role="img"
      className={cx("inline-block size-4 shrink-0", className)}
    >
      <span className="sr-only">{label ?? state}</span>
      <svg
        data-slot="dot-matrix-grid"
        aria-hidden
        viewBox="0 0 20 20"
        fill="currentColor"
        className="size-full"
      >
        {Array.from({ length: CELL_COUNT }, (_, i) => {
          if (!lit.has(i)) return null;
          const row = Math.floor(i / GRID);
          const col = i % GRID;
          return (
            <rect
              key={i}
              data-slot="dot-matrix-dot"
              data-on="true"
              x={0.85 + col * 4}
              y={0.85 + row * 4}
              width={2.3}
              height={2.3}
              fill="currentColor"
              shapeRendering="crispEdges"
            />
          );
        })}
      </svg>
    </span>
  );
}

export function litCellsFor(state: DotMatrixState, frame = 0): readonly number[] {
  const frames = PATTERNS[state];
  return frames[frame] ?? frames[0];
}

export { DotMatrix, dotMatrixStates, PATTERNS };
