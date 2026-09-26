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

/**
 * Anchor-focused solve (v18): the focused tile grows in place while the rest
 * reflow around it.
 *
 * The owner found the full re-solve hard to follow — the open module jumped
 * to a new spot every step. So the rest layout (`rest`, solved with
 * unfocused weights) is the stable map: the focused tile keeps its rest
 * top-left (clamped into the box when its grown size would overflow) and the
 * non-focused tiles repack into the four regions around it (top / bottom /
 * left / right strips), each region filled by its own constrained solve.
 * Tiles are assigned to the region holding their rest centre, so a tile stays
 * near its resting zone; within a region, weight ratios stay exact. Global
 * cross-region proportions are approximate rather than exact — followability
 * won that trade. Pure in its inputs; covered in `treemap.test.ts`.
 */
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

/**
 * Anchor-focused solve: the focused tile keeps its rest top-left and grows
 * to `focusedSize` (clamped into the box); every other tile repacks into the
 * strips around it. See the `TreemapMins` docblock above for the why.
 *
 * Tiles go to the strip holding their rest centre (nearest strip wins ties
 * and covers centres swallowed by the grown focused rect); each strip is
 * filled by its own constrained solve, so weight ratios hold within a strip.
 * Strips too thin to hold anything are skipped and their tiles fall through
 * to the nearest usable strip, so the field always stays a full partition —
 * best-effort minimums, never overlaps, never NaNs.
 */
export function treemapAnchored(
  weights: number[],
  W: number,
  H: number,
  mins: TreemapMins[],
  rest: TreemapRect[],
  focusIndex: number,
  focusedSize: { w: number; h: number },
): TreemapRect[] {
  const out: TreemapRect[] = new Array(weights.length);
  const anchor = rest[focusIndex];
  if (!anchor) return treemapAreasConstrained(weights, W, H, mins);
  const min = mins[focusIndex];
  const fw = Math.min(Math.max(focusedSize.w, min?.minW ?? 0), W);
  const fh = Math.min(Math.max(focusedSize.h, min?.minH ?? 0), H);
  const fx = Math.min(Math.max(anchor.x, 0), Math.max(W - fw, 0));
  const fy = Math.min(Math.max(anchor.y, 0), Math.max(H - fh, 0));
  out[focusIndex] = { x: fx, y: fy, w: fw, h: fh };

  interface Strip {
    x: number;
    y: number;
    w: number;
    h: number;
  }
  const strips: Strip[] = [
    { x: 0, y: 0, w: W, h: fy },
    { x: 0, y: fy + fh, w: W, h: H - fy - fh },
    { x: 0, y: fy, w: fx, h: fh },
    { x: fx + fw, y: fy, w: W - fx - fw, h: fh },
  ].filter((s) => s.w > 4 && s.h > 4);
  if (strips.length === 0) return out;

  const centre = (i: number) => {
    const r = rest[i];
    return { x: r.x + r.w / 2, y: r.y + r.h / 2 };
  };
  const contains = (s: Strip, p: { x: number; y: number }) =>
    p.x >= s.x && p.x <= s.x + s.w && p.y >= s.y && p.y <= s.y + s.h;
  const distance = (s: Strip, p: { x: number; y: number }) => {
    const dx = Math.max(s.x - p.x, 0, p.x - (s.x + s.w));
    const dy = Math.max(s.y - p.y, 0, p.y - (s.y + s.h));
    return dx * dx + dy * dy;
  };
  const buckets: number[][] = strips.map(() => []);
  weights.forEach((_, i) => {
    if (i === focusIndex) return;
    const p = centre(i);
    let best = 0;
    let bestScore: number | null = null;
    strips.forEach((s, k) => {
      const score = contains(s, p) ? -1 : distance(s, p);
      if (bestScore === null || score < bestScore) {
        bestScore = score;
        best = k;
      }
    });
    buckets[best].push(i);
  });

  strips.forEach((s, k) => {
    const members = buckets[k];
    if (members.length === 0) return;
    if (members.length === 1) {
      out[members[0]] = { ...s };
      return;
    }
    const sub = treemapAreasConstrained(
      members.map((i) => weights[i]),
      s.w,
      s.h,
      members.map((i) => mins[i]),
    );
    members.forEach((id, j) => {
      const r = sub[j];
      out[id] = { x: s.x + r.x, y: s.y + r.y, w: r.w, h: r.h };
    });
  });

  /* A tile lands here only when every strip was unusable — unreachable while
     the focused tile leaves any room, but a full partition beats a hole. */
  weights.forEach((_, i) => {
    out[i] ??= { ...out[focusIndex] };
  });
  return out;
}
