import { treemapAnchored } from "../../../packages/ui/src/components/data-layout/treemap";
import { COLS, MIN_H, MIN_W, ROWS, type Layout, type Placement } from "./grid";

/**
 * Open one block in place, like the site's module mosaic (kit `ModuleGrid`):
 * the open block keeps its top-left and grows, and every other block repacks
 * into the strips around it (`treemapAnchored`). Nothing covers the grid, and
 * no block leaves it. The web desk and this client share the solve.
 *
 * The treemap solves in continuous units and drops strips under 4 units, so
 * one grid cell is `UNIT` units here. The rects snap back to whole cells.
 */
const UNIT = 10;
/** The open block takes at least this much more of each side than its rest. */
const GROW = 1.5;

/** Cells the open block asks for. The solve keeps it inside the grid. */
export type Need = { w: number; h: number };

const clamp = (v: number, lo: number, hi: number) => Math.max(lo, Math.min(hi, v));

const hit = (a: Placement, b: Placement) =>
  a.x < b.x + b.w && b.x < a.x + a.w && a.y < b.y + b.h && b.y < a.y + a.h;

/** Every block on the grid, at least one cell, no overlaps. */
function sound(layout: Layout): boolean {
  if (layout.some((p) => p.w < 1 || p.h < 1 || p.x < 1 || p.y < 1 || p.x + p.w - 1 > COLS || p.y + p.h - 1 > ROWS)) return false;
  return !layout.some((a, i) => layout.some((b, j) => i < j && hit(a, b)));
}

/** The size the open block asks for: its content, and never less than `GROW` times its rest. */
export function openSize(rest: Placement, need?: Need): Need {
  return {
    w: clamp(Math.max(Math.ceil(rest.w * GROW), Math.ceil(need?.w ?? 0)), rest.w, COLS),
    h: clamp(Math.max(Math.ceil(rest.h * GROW), Math.ceil(need?.h ?? 0)), rest.h, ROWS),
  };
}

/** The layout with `id` open. Unknown id, a lone block, or a solve that will not snap returns the rest layout. */
export function expandLayout(layout: Layout, id: string | null, need?: Need): Layout {
  const index = id === null ? -1 : layout.findIndex((p) => p.id === id);
  const open = layout[index];
  if (!open || layout.length < 2) return layout;
  const want = openSize(open, need);
  const rest = layout.map((p) => ({ x: (p.x - 1) * UNIT, y: (p.y - 1) * UNIT, w: p.w * UNIT, h: p.h * UNIT }));
  const weights = layout.map((p, i) => (i === index ? want.w * want.h : p.w * p.h));
  const mins = layout.map((p, i) =>
    i === index ? { minW: open.w * UNIT, minH: open.h * UNIT } : { minW: MIN_W * UNIT, minH: MIN_H * UNIT },
  );
  const rects = treemapAnchored(weights, COLS * UNIT, ROWS * UNIT, mins, rest, index, { w: want.w * UNIT, h: want.h * UNIT });
  const next = rects.map((r, i): Placement => {
    const x0 = Math.round(r.x / UNIT);
    const y0 = Math.round(r.y / UNIT);
    return {
      id: layout[i]!.id,
      x: x0 + 1,
      y: y0 + 1,
      w: Math.round((r.x + r.w) / UNIT) - x0,
      h: Math.round((r.y + r.h) / UNIT) - y0,
    };
  });
  return sound(next) ? next : layout;
}
