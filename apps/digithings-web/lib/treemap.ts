/**
 * Squarified treemap partition (the module mosaic's packing, v17).
 *
 * Splits a W×H box into one rectangle per weight, in order, with areas ∝
 * weights and a worst-aspect-first row choice so tiles stay squarish as they
 * reflow. Pure in `(weights, W, H)`, so the same focus always draws the same
 * mosaic. Framework-free so it can be unit-tested without a DOM.
 *
 * Focusing a tile re-solves the whole partition, so tiles change neighbours
 * freely instead of stretching their row-mates: proportions live in the
 * weights, not in row membership. The render insets each rect by half of the
 * gutter.
 */
export interface TreemapRect {
  x: number;
  y: number;
  w: number;
  h: number;
}

export function treemapAreas(weights: number[], W: number, H: number): TreemapRect[] {
  const total = weights.reduce((acc, w) => acc + w, 0) || 1;
  const scale = (W * H) / total;
  const items = weights.map((w, i) => ({ area: w * scale, i }));
  const out: TreemapRect[] = new Array(weights.length);
  const rowArea = (row: { area: number }[]) => row.reduce((acc, r) => acc + r.area, 0);
  const worst = (row: { area: number }[], side: number) => {
    const s = rowArea(row);
    const hi = Math.max(...row.map((r) => r.area));
    const lo = Math.min(...row.map((r) => r.area));
    return Math.max((side * side * hi) / (s * s) || 0, (s * s) / (side * side * lo) || 0);
  };
  const layRow = (
    row: { area: number; i: number }[],
    x: number,
    y: number,
    w: number,
    h: number,
    horizontal: boolean,
  ) => {
    const s = rowArea(row);
    if (horizontal) {
      const rh = s / w;
      let rx = x;
      row.forEach((r) => {
        const rw = r.area / rh;
        out[r.i] = { x: rx, y, w: rw, h: rh };
        rx += rw;
      });
      return { x, y: y + rh, w, h: h - rh };
    }
    const cw = s / h;
    let ry = y;
    row.forEach((r) => {
      const rh = r.area / cw;
      out[r.i] = { x, y: ry, w: cw, h: rh };
      ry += rh;
    });
    return { x: x + cw, y, w: w - cw, h };
  };
  let x = 0;
  let y = 0;
  let w = W;
  let h = H;
  let row: { area: number; i: number }[] = [];
  const rest = [...items];
  while (rest.length > 0) {
    /* The row spans the SHORTEST side of the remaining box: a wide remainder
       packs a vertical column (full height), a tall remainder a horizontal
       strip (full width). Spanning the longest side instead reads better in
       prose but draws full-width slivers for every light tile past the first
       row (measured: eleven tiles, ten of them 1216px-wide slivers) — the
       `worst` metric above only agrees with the layout when the two share
       this orientation. */
    const horizontal = w < h;
    const side = Math.min(w, h);
    const next = rest[0];
    if (row.length === 0 || worst([...row, next], side) <= worst(row, side)) {
      row.push(next);
      rest.shift();
    } else {
      ({ x, y, w, h } = layRow(row, x, y, w, h, horizontal));
      row = [];
    }
  }
  if (row.length > 0) layRow(row, x, y, w, h, w < h);
  return out;
}

export interface TreemapMins {
  minW: number;
  minH: number;
}

/**
 * Constrained solve: every tile's weight first covers its minimum area
 * outright (margin 1.5x for aspect slop), then one pure partition, then a
 * short gentle polish for packing-geometry residuals.
 *
 * Deliberately NOT an iterative weight chase: when several tiles violate at
 * once, joint multiplicative lifts freeze their ratios and can starve a
 * small tile forever (measured live: a roadmap tile ended 101px wide against
 * a 184px minimum while the loop insisted it was "lifting" it). Direct
 * floors cannot freeze — areas always match weights exactly — so the minimums
 * hold jointly whenever the box can fit them. Past that (a box smaller than
 * every minimum combined) it degrades best-effort: still a full partition,
 * still finite, still no overlaps.
 *
 * Squarified packing assumes descending weights, but boosts, floors and
 * measured top-ups can invert the LOC order (a floored roadmap can outweigh
 * digiquant), which degrades aspect quality into slivers — measured live as
 * 107px-wide resting tiles with clipped titles beside a 776px focused one.
 * So every solve sorts descending first and maps rects back; packing quality
 * never depends on focus luck. The sort is stable, so equal weights keep
 * their LOC order.
 *
 * The landing mosaic uses this to guarantee the owner's floor: every tile
 * wide enough for its title + version with padding, every focused tile large
 * enough for its detail. Minimums are in cell space (the render insets the
 * gutter afterwards), so callers inflate them by the gutter.
 */
export function treemapAreasConstrained(
  weights: number[],
  W: number,
  H: number,
  mins: TreemapMins[],
  maxIters = 3,
): TreemapRect[] {
  const total = weights.reduce((acc, w) => acc + w, 0) || 1;
  const boxArea = Math.max(W * H, 1);
  const order = weights.map((_, i) => i).sort((a, b) => weights[b] - weights[a]);
  const sorted = order.map((i) => weights[i]);
  const sortedMins = order.map((i) => mins[i]);
  const floored = sorted.map((w, k) => {
    const m = sortedMins[k];
    if (!m) return w;
    return Math.max(w, ((m.minW * m.minH * 1.5) / boxArea) * total);
  });
  const lifted = [...floored];
  const solveAll = () => treemapAreas(lifted, W, H);
  let sortedRects = solveAll();
  for (let k = 0; k < maxIters; k++) {
    let clean = true;
    for (let s = 0; s < sortedRects.length; s++) {
      const m = sortedMins[s];
      if (!m) continue;
      const r = sortedRects[s];
      if (r.w < m.minW || r.h < m.minH) {
        clean = false;
        lifted[s] *= 1.3;
      }
    }
    if (clean) break;
    sortedRects = solveAll();
  }
  const out: TreemapRect[] = new Array(weights.length);
  sortedRects.forEach((r, s) => {
    out[order[s]] = r;
  });
  return out;
}
