/**
 * Block grid model. A page is COLS × ROWS cells that always fill the viewport
 * (no page scroll); a placement is a 1-based rectangle of cells. Pure functions
 * only, so the behaviour is testable without React.
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
  return { id: p.id, w, h, x: clamp(Math.round(p.x), 1, COLS - w + 1), y: clamp(Math.round(p.y), 1, ROWS - h + 1) };
};

const hit = (a: Placement, b: Placement) => a.x < b.x + b.w && b.x < a.x + a.w && a.y < b.y + b.h && b.y < a.y + a.h;

/**
 * Put `moved` where it asks and push anything it overlaps downward, cascading.
 * Returns null when the result would not fit in the grid — callers keep the old layout.
 */
export function place(layout: Layout, moved: Placement): Layout | null {
  const next = layout.map((p) => (p.id === moved.id ? fit(moved) : { ...p }));
  const queue = [next.find((p) => p.id === moved.id)!];
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
 * Full-grid fallback: when `moved` lands on exactly one other block and a push-down has no room,
 * trade places — the other block takes the mover's old rectangle (its own size kept, clamped in).
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

/** Keep a resize inside the grid by capping w/h at the edge, so x/y (the origin) never move. */
export const clampSize = (p: Placement): Placement => ({
  ...p,
  w: Math.min(p.w, COLS - p.x + 1),
  h: Math.min(p.h, ROWS - p.y + 1),
});

/**
 * First free spot (scan row-major) for a new block. Tries the default size, then shrinks
 * (largest area first) down to MIN_W × MIN_H; null only when no free rectangle exists at all.
 */
export function slot(layout: Layout, id: string, w = 4, h = 4): Placement | null {
  const sizes: [number, number][] = [];
  for (let ww = w; ww >= MIN_W; ww--) for (let hh = h; hh >= MIN_H; hh--) sizes.push([ww, hh]);
  sizes.sort((a, b) => b[0] * b[1] - a[0] * a[1]);
  for (const [sw, sh] of sizes) {
    for (let y = 1; y + sh - 1 <= ROWS; y++) {
      for (let x = 1; x + sw - 1 <= COLS; x++) {
        const p = { id, x, y, w: sw, h: sh };
        if (!layout.some((o) => hit(p, o))) return p;
      }
    }
  }
  return null;
}

/** Accept only well-formed, in-bounds, non-overlapping placements of known ids; else fall back. */
export function parse(raw: unknown, known: Set<string>, fallback: Layout): Layout {
  if (!Array.isArray(raw)) return fallback;
  const out: Layout = [];
  for (const r of raw) {
    if (!r || typeof r !== 'object') return fallback;
    const { id, x, y, w, h } = r as Placement;
    if (typeof id !== 'string' || !known.has(id) || ![x, y, w, h].every(Number.isFinite)) return fallback;
    const f = fit({ id, x, y, w, h });
    if (f.x !== x || f.y !== y || f.w !== w || f.h !== h) return fallback;
    out.push(f);
  }
  if (new Set(out.map((p) => p.id)).size !== out.length) return fallback;
  return out.some((a, i) => out.some((b, j) => i < j && hit(a, b))) ? fallback : out;
}
