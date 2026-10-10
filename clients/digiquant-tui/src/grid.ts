/**
 * 12×12 block grid. A placement is a 1-based rectangle. Move pushes overlaps
 * downward; resize keeps the origin and stops at the edge.
 */
export const COLS = 12;
export const ROWS = 12;
export const MIN_W = 2;
export const MIN_H = 2;

export type Placement = { id: string; x: number; y: number; w: number; h: number };
export type Layout = Placement[];

const clamp = (v: number, lo: number, hi: number) => Math.max(lo, Math.min(hi, v));

export const fit = (p: Placement): Placement => {
  const w = clamp(Math.round(p.w), MIN_W, COLS);
  const h = clamp(Math.round(p.h), MIN_H, ROWS);
  return {
    id: p.id,
    w,
    h,
    x: clamp(Math.round(p.x), 1, COLS - w + 1),
    y: clamp(Math.round(p.y), 1, ROWS - h + 1),
  };
};

const hit = (a: Placement, b: Placement) =>
  a.x < b.x + b.w && b.x < a.x + a.w && a.y < b.y + b.h && b.y < a.y + a.h;

/** Put `moved` where it asks and push overlaps downward. Null when it will not fit. */
export function place(layout: Layout, moved: Placement): Layout | null {
  const next = layout.map((p) => (p.id === moved.id ? fit(moved) : { ...p }));
  const found = next.find((p) => p.id === moved.id);
  if (!found) return null;
  const queue = [found];
  for (let guard = 0; queue.length && guard < 500; guard++) {
    const anchor = queue.shift()!;
    for (const p of next) {
      if (p.id === anchor.id || !hit(anchor, p)) continue;
      p.y = anchor.y + anchor.h;
      if (p.y + p.h - 1 > ROWS) return null;
      queue.push(p);
    }
  }
  return next.some((a, i) => next.some((b, j) => i < j && hit(a, b))) ? null : next;
}

/**
 * Trade the two rectangles when a push-down has no room and the mover covers
 * exactly one block. Each block keeps its size and takes the other's origin.
 */
export function swap(layout: Layout, moved: Placement): Layout | null {
  const from = layout.find((p) => p.id === moved.id);
  if (!from) return null;
  const m = fit(moved);
  const over = layout.filter((p) => p.id !== m.id && hit(m, p));
  if (over.length !== 1) return null;
  const other = fit({ ...over[0], x: from.x, y: from.y });
  const next = layout.map((p) => (p.id === m.id ? m : p.id === other.id ? other : p));
  return next.some((a, i) => next.some((b, j) => i < j && hit(a, b))) ? null : next;
}

/**
 * On a full page, a one-cell bump still has to move. Exchange the mover's
 * rectangle with the single block it hits, so both slots stay filled.
 */
function trade(layout: Layout, moved: Placement): Layout | null {
  const from = layout.find((p) => p.id === moved.id);
  if (!from) return null;
  const over = layout.filter((p) => p.id !== moved.id && hit(fit(moved), p));
  if (over.length !== 1) return null;
  const other = over[0];
  const next = layout.map((p) => {
    if (p.id === from.id) return { id: p.id, x: other.x, y: other.y, w: other.w, h: other.h };
    if (p.id === other.id) return { id: p.id, x: from.x, y: from.y, w: from.w, h: from.h };
    return { ...p };
  });
  return next.some((a, i) => next.some((b, j) => i < j && hit(a, b))) ? null : next;
}

/** Cap w/h at the grid edge so the origin stays put. */
export const clampSize = (p: Placement): Placement => ({
  ...p,
  w: Math.min(p.w, COLS - p.x + 1),
  h: Math.min(p.h, ROWS - p.y + 1),
});

/**
 * Move (`sizing` false) or resize the block by one step.
 * Returns null when the block is missing or the grid has no room.
 */
export function nudge(layout: Layout, id: string, dx: number, dy: number, sizing: boolean): Layout | null {
  const cur = layout.find((p) => p.id === id);
  if (!cur || (dx === 0 && dy === 0)) return null;
  if (sizing) {
    const w = cur.w + dx;
    const h = cur.h + dy;
    if (w < MIN_W || h < MIN_H) return null;
    const next = clampSize({ ...cur, w, h });
    if (next.w === cur.w && next.h === cur.h) return null;
    return place(layout, next);
  }
  const moved = { ...cur, x: cur.x + dx, y: cur.y + dy };
  return place(layout, moved) ?? swap(layout, moved) ?? trade(layout, moved);
}
