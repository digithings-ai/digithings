"use client";

import { useEffect, useState, type ComponentProps } from "react";
import { cn } from "@/lib/utils";

/**
 * Gallery fork of assistant-ui DotMatrix. Cubes snap on/off (no fade).
 * Motion states are agent actions; caution/error/success stay as glyphs.
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

const glyph = (dots: [number, number][]) => dots.map(([row, col]) => idx(row, col));

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
} as const;

export type DotMatrixState = keyof typeof PATTERNS;

const dotMatrixStates = Object.keys(PATTERNS) as readonly DotMatrixState[];

export type DotMatrixProps = Omit<ComponentProps<"span">, "children"> & {
  state?: DotMatrixState;
  label?: string;
};

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
      data-slot="dot-matrix"
      data-state={state}
      role="status"
      className={cn("inline-block size-4 shrink-0", className)}
      {...props}
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

export { DotMatrix, dotMatrixStates };
