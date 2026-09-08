"use client";

import { useEffect, useState, type ComponentProps } from "react";

/**
 * 5×5 snap-on/off cube matrix. Motion states are agent actions; static
 * states are status and chrome glyphs. Unlit cells stay in the SVG so CSS
 * can draw a hairline grid. No opacity ease — cubes are on or off.
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

/** Clockwise inner 3×3 rim. */
const INNER_RING = [
  idx(1, 1),
  idx(1, 2),
  idx(1, 3),
  idx(2, 3),
  idx(3, 3),
  idx(3, 2),
  idx(3, 1),
  idx(2, 1),
];

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

const hold = (distances: number[]) => distances.map((d) => cellsAt(d));
const fill = (distances: number[]) => distances.map((d) => cellsAtMost(d));

const PATTERNS = {
  idle: [CORNERS],
  /** One cube around the rim. */
  loading: PERIMETER.map((cell) => [cell]),
  /** Hollow ring in, hold center, ring out. */
  thinking: hold([2, 2, 1, 1, 0, 0, 1, 1, 2, 2]),
  /** Smaller orbit — a tool is in flight. */
  tool: INNER_RING.map((cell) => [cell]),
  /** Scanline down the rows. */
  executing: [0, 1, 2, 3, 4].map(rowCells),
  /** Scanline across the columns (web search). */
  searching: [0, 1, 2, 3, 4].map(colCells),
  /** Filled square shrinks to the center, then grows back. */
  compacting: fill([2, 2, 1, 1, 0, 0, 1, 1, 2, 2]),
  warning: [BANG],
  error: [CROSS],
  success: [CHECK],
  /** Two offset pages. */
  copy: [
    glyph([
      [0, 1],
      [0, 2],
      [0, 3],
      [1, 0],
      [1, 1],
      [1, 3],
      [2, 0],
      [2, 3],
      [2, 4],
      [3, 0],
      [3, 4],
      [4, 1],
      [4, 2],
      [4, 3],
      [4, 4],
    ]),
  ],
  /** Underscore + block caret. */
  edit: [
    glyph([
      [1, 0],
      [1, 1],
      [1, 2],
      [2, 0],
      [2, 1],
      [2, 2],
      [0, 4],
      [1, 4],
      [2, 4],
      [3, 4],
    ]),
  ],
  /** Clip / staple. */
  attach: [
    glyph([
      [0, 1],
      [0, 2],
      [0, 3],
      [1, 1],
      [2, 1],
      [2, 2],
      [2, 3],
      [3, 1],
      [3, 3],
      [4, 1],
      [4, 2],
    ]),
  ],
  /** Enter / return cluster. */
  send: [
    glyph([
      [0, 3],
      [0, 4],
      [1, 4],
      [2, 0],
      [2, 1],
      [2, 2],
      [2, 3],
      [2, 4],
      [3, 1],
      [4, 0],
      [4, 1],
      [4, 2],
    ]),
  ],
  /** Three cubes on the mid row. */
  more: [glyph([[2, 0], [2, 2], [2, 4]])],
  /** Open cycle. */
  refresh: [
    glyph([
      [0, 1],
      [0, 2],
      [0, 3],
      [1, 0],
      [2, 1],
      [2, 2],
      [2, 3],
      [3, 4],
      [4, 1],
      [4, 2],
      [4, 3],
    ]),
  ],
  /** Arrow out, north-east. */
  export: [
    glyph([
      [0, 2],
      [0, 3],
      [0, 4],
      [1, 3],
      [1, 4],
      [2, 2],
      [3, 1],
      [4, 0],
    ]),
  ],
  /** Arrow into a tray. */
  download: [
    glyph([
      [0, 2],
      [1, 1],
      [1, 2],
      [1, 3],
      [2, 2],
      [3, 0],
      [3, 1],
      [3, 2],
      [3, 3],
      [3, 4],
    ]),
  ],
  /** Stop square. */
  stop: [
    glyph([
      [1, 1],
      [1, 2],
      [1, 3],
      [2, 1],
      [2, 2],
      [2, 3],
      [3, 1],
      [3, 2],
      [3, 3],
    ]),
  ],
  /** Small × (softer than error). */
  remove: [glyph([[1, 1], [1, 3], [2, 2], [3, 1], [3, 3]])],
  /** Down chevron. */
  scroll: [glyph([[1, 0], [1, 4], [2, 1], [2, 3], [3, 2]])],
  /** Left chevron. */
  prev: [glyph([[0, 2], [1, 1], [2, 0], [3, 1], [4, 2]])],
  /** Right arrow with a shaft — distinct from the user `>`. */
  next: [
    glyph([
      [0, 2],
      [1, 3],
      [2, 0],
      [2, 1],
      [2, 2],
      [2, 3],
      [2, 4],
      [3, 3],
      [4, 2],
    ]),
  ],
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
  /** Plus. */
  plus: [
    glyph([
      [0, 2],
      [1, 2],
      [2, 0],
      [2, 1],
      [2, 2],
      [2, 3],
      [2, 4],
      [3, 2],
      [4, 2],
    ]),
  ],
  /** Disclosure V. */
  expand: [
    glyph([
      [1, 0],
      [1, 1],
      [1, 2],
      [1, 3],
      [1, 4],
      [2, 1],
      [2, 2],
      [2, 3],
      [3, 2],
    ]),
  ],
  /** User role — open `>`. */
  user: [glyph([[0, 1], [1, 2], [2, 3], [3, 2], [4, 1]])],
  /** Assistant role — filled `▸`. */
  assistant: [
    glyph([
      [0, 0],
      [1, 0],
      [1, 1],
      [2, 0],
      [2, 1],
      [2, 2],
      [3, 0],
      [3, 1],
      [4, 0],
    ]),
  ],
  /** Example / suggestion row — `>` shifted right. */
  example: [glyph([[0, 2], [1, 3], [2, 4], [3, 3], [4, 2]])],
  /** System aside — center cube. */
  system: [glyph([[2, 2]])],
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
          const row = Math.floor(i / GRID);
          const col = i % GRID;
          return (
            <rect
              key={i}
              data-slot="dot-matrix-dot"
              data-on={lit.has(i) ? "true" : "false"}
              x={0.85 + col * 4}
              y={0.85 + row * 4}
              width={2.3}
              height={2.3}
              fill="currentColor"
              fillOpacity={lit.has(i) ? 1 : 0}
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
