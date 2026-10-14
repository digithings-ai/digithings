import { cellAt, cellPoint, hash, paintMax, type FieldState, type Grid, type Subject } from "./pixel-field-core";

/**
 * DIG-3319 round 2: an embedding-space map as the hero's base drawing.
 *
 * Same three layers as the production world map (`../pixel-field.ts`), with
 * the subject swapped for what AI infra does with your data:
 *
 * - land mask  -> clusters of a 2D-projected knowledge base. Dense cores, edges
 *   that dither out into loose points, a few stray outliers. Seeded, so the
 *   "geography" is the same on every load.
 * - exchange hubs -> topic centroids, one per cluster, pulsing like the hubs.
 * - market hours / day-night -> an index sweep that drifts across the map
 *   (fresh embeddings brighter), and queries: a point lands, lines reach out to
 *   its nearest topics, and the hit topics run hot for a few seconds.
 *
 * Three compositions share this file; they only differ in cluster layout and
 * whether the clusters drift.
 */

export type EmbeddingLayout = "continents" | "scatter" | "drift";

type Blob = { x: number; y: number; r: number; phase: number };
type Cluster = { blobs: Blob[] };
// x and y are fractions of width and height; size is a fraction of height.
type Spec = { x: number; y: number; size: number; stretch: number; angle: number; parts: number };

const CONTINENTS: Spec[] = [
  { x: 0.07, y: 0.3, size: 0.3, stretch: 1.7, angle: 0.3, parts: 7 },
  { x: 0.19, y: 0.8, size: 0.21, stretch: 1.4, angle: -0.5, parts: 5 },
  { x: 0.41, y: 0.08, size: 0.13, stretch: 2.2, angle: 0.1, parts: 4 },
  { x: 0.64, y: 0.88, size: 0.16, stretch: 1.9, angle: 0.15, parts: 4 },
  { x: 0.83, y: 0.36, size: 0.31, stretch: 1.5, angle: -0.25, parts: 8 },
  { x: 0.96, y: 0.82, size: 0.15, stretch: 1.1, angle: 0, parts: 3 },
  { x: 0.31, y: 0.52, size: 0.07, stretch: 1, angle: 0, parts: 2 },
  { x: 0.59, y: 0.27, size: 0.06, stretch: 1, angle: 0, parts: 2 },
  { x: 0.73, y: 0.64, size: 0.08, stretch: 1.2, angle: 0.6, parts: 2 },
  { x: 0.03, y: 0.66, size: 0.06, stretch: 1, angle: 0, parts: 2 },
];

function mulberry32(seed: number): () => number {
  let state = seed;
  return () => {
    state = (state + 0x6d2b79f5) | 0;
    let t = Math.imul(state ^ (state >>> 15), 1 | state);
    t = (t + Math.imul(t ^ (t >>> 7), 61 | t)) ^ t;
    return ((t ^ (t >>> 14)) >>> 0) / 4294967296;
  };
}

/** Scatter: many smaller islands, placed by seeded rejection sampling, thin in the middle. */
function scatterSpecs(rand: () => number): Spec[] {
  const specs: Spec[] = [];
  for (let tries = 0; specs.length < 16 && tries < 600; tries++) {
    const x = rand();
    const y = 0.05 + 0.9 * rand();
    const centre = Math.hypot((x - 0.5) / 0.3, (y - 0.46) / 0.45);
    if (centre < 1 && rand() < 0.75) continue;
    if (specs.some((s) => Math.hypot((s.x - x) * 2.6, s.y - y) < 0.24)) continue;
    specs.push({ x, y, size: 0.08 + 0.09 * rand(), stretch: 1 + 0.8 * rand(), angle: 3 * rand(), parts: 2 + Math.floor(3 * rand()) });
  }
  return specs;
}

/** Each cluster is a short random walk of overlapping blobs, in height units. */
function buildClusters(specs: Spec[], aspect: number, rand: () => number): Cluster[] {
  return specs.map((spec) => {
    const blobs: Blob[] = [];
    let x = spec.x * aspect;
    let y = spec.y;
    for (let n = 0; n < spec.parts; n++) {
      blobs.push({ x, y, r: spec.size * (0.38 + 0.32 * rand()), phase: 6.28 * rand() });
      const turn = spec.angle + (rand() - 0.5) * 1.6 + (n % 2 ? Math.PI : 0);
      const step = spec.size * (0.35 + 0.35 * rand());
      x = spec.x * aspect + Math.cos(turn) * step * spec.stretch * (1 + n * 0.25);
      y = spec.y + Math.sin(turn) * step * (1 + n * 0.15);
    }
    return { blobs };
  });
}

function smooth(a: number, b: number, v: number): number {
  const t = Math.min(1, Math.max(0, (v - a) / (b - a)));
  return t * t * (3 - 2 * t);
}

type Query = { x: number; y: number; start: number; hits: number[] };

export function createEmbeddingSubject(layout: EmbeddingLayout): (grid: Grid) => Subject {
  return (grid) => {
    const count = grid.cols * grid.rows;
    const aspect = grid.width / grid.height;
    const rand = mulberry32(layout === "scatter" ? 3319 : 2203);
    const specs = layout === "scatter" ? scatterSpecs(rand) : CONTINENTS;
    const clusters = buildClusters(specs, aspect, rand);
    const drifting = layout === "drift";
    const outliers = layout === "scatter" ? 0.012 : 0.005;

    // Same centre clearing as production, so the headline stays readable.
    const vignette = new Float32Array(count);
    const cx = grid.width / 2;
    const cy = grid.height * 0.46;
    const rx = grid.width * (grid.small ? 0.62 : 0.34);
    const ry = grid.height * 0.5;
    const ux = new Float32Array(count);
    const uy = new Float32Array(count);
    for (let i = 0; i < count; i++) {
      const p = cellPoint(grid, i);
      const t = Math.min(1, Math.max(0, (Math.hypot((p.x - cx) / rx, (p.y - cy) / ry) - 0.7) / 0.55));
      vignette[i] = 0.08 + 0.92 * t * t * (3 - 2 * t);
      ux[i] = p.x / grid.height;
      uy[i] = p.y / grid.height;
    }

    const blobAt = (blob: Blob, time: number) =>
      drifting
        ? {
            x: blob.x + Math.sin(time / 9000 + blob.phase) * blob.r * 0.4,
            y: blob.y + Math.cos(time / 11000 + blob.phase * 1.3) * blob.r * 0.3,
            r: blob.r * (0.9 + 0.12 * Math.sin(time / 7000 + blob.phase)),
          }
        : blob;

    const density = new Float32Array(count);
    const hubs: { x: number; y: number }[] = clusters.map(() => ({ x: 0, y: 0 }));
    let densityAt = -Infinity;
    function refresh(time: number) {
      densityAt = time;
      const placed = clusters.map((c) => c.blobs.map((b) => blobAt(b, time)));
      placed.forEach((blobs, n) => {
        const head = blobs[0];
        if (head) hubs[n] = { x: head.x * grid.height, y: head.y * grid.height };
      });
      for (let i = 0; i < count; i++) {
        let d = 0;
        for (const blobs of placed) {
          for (const b of blobs) {
            const dx = (ux[i] ?? 0) - b.x;
            const dy = (uy[i] ?? 0) - b.y;
            const q = (dx * dx + dy * dy) / (b.r * b.r);
            if (q < 9) d += Math.exp(-q);
          }
        }
        density[i] = 0.62 * smooth(0.22, 1.1, d) + outliers;
      }
    }
    refresh(0);

    const lit = new Uint8Array(count);
    const flicker = new Float32Array(count);
    for (let i = 0; i < count; i++) {
      lit[i] = Math.random() < (density[i] ?? 0) ? 1 : 0;
      flicker[i] = 0.6 + 0.4 * Math.random();
    }

    const hot = new Float32Array(hubs.length);
    const queries: Query[] = [];
    let nextQuery = 1500;
    let last = 0;
    const ring = Math.max(40, 6 * grid.pitch);
    const reach = Math.ceil(ring / grid.pitch) + 1;

    function line(state: FieldState, ax: number, ay: number, bx: number, by: number, u: number, alpha: number) {
      const len = Math.hypot(bx - ax, by - ay);
      const steps = Math.max(1, Math.ceil((len * u) / (grid.pitch * 0.7)));
      for (let s = 0; s <= steps; s++) {
        const f = (s / steps) * u;
        const i = cellAt(grid, ax + (bx - ax) * f, ay + (by - ay) * f);
        // Brightest at the travelling head, fading back toward the query.
        if (i >= 0) paintMax(state, i, alpha * (0.35 + 0.65 * (s / steps)) * (vignette[i] ?? 0), 1);
      }
    }

    function ringAt(state: FieldState, x: number, y: number, radius: number, alpha: number, kind: number) {
      const center = cellAt(grid, x, y);
      if (center < 0) return;
      const col = center % grid.cols;
      const row = (center - col) / grid.cols;
      for (let dy = -reach; dy <= reach; dy++) {
        for (let dx = -reach; dx <= reach; dx++) {
          const c = col + dx;
          const r = row + dy;
          if (c < 0 || r < 0 || c >= grid.cols || r >= grid.rows) continue;
          const i = r * grid.cols + c;
          const p = cellPoint(grid, i);
          if (Math.abs(Math.hypot(p.x - x, p.y - y) - radius) > 0.6 * grid.pitch) continue;
          paintMax(state, i, alpha * (vignette[i] ?? 0), kind);
        }
      }
    }

    return {
      update(time: number, state: FieldState) {
        const dt = Math.min(100, time - last);
        last = time;
        if (drifting && time - densityAt > 300) refresh(time);

        const flips = Math.max(1, Math.round(0.006 * count));
        for (let n = 0; n < flips; n++) {
          const i = Math.floor(Math.random() * count);
          lit[i] = Math.random() < (density[i] ?? 0) ? 1 : 0;
        }

        // Index sweep: a soft band crossing the map every ~40s.
        const sweep = (((time / 40000) % 1.3) - 0.15) * grid.width;
        const band = 0.13 * grid.width;
        for (let i = 0; i < count; i++) {
          state.kind[i] = 0;
          if (!lit[i]) {
            state.target[i] = 0;
            continue;
          }
          const off = ((ux[i] ?? 0) * grid.height - sweep) / band;
          const fresh = 0.82 + 0.5 * Math.exp(-off * off);
          state.target[i] = 0.09 * fresh * (flicker[i] ?? 1) * (vignette[i] ?? 0);
        }

        for (let n = 0; n < hot.length; n++) hot[n] = Math.max(0, (hot[n] ?? 0) - dt / 4500);

        hubs.forEach((hub, n) => {
          const heat = hot[n] ?? 0;
          const period = 3600 + 3800 * hash(n, 7);
          const phase = (time + 6000 * hash(n, 3)) % period;
          if (phase < 1600) {
            const t = phase / 1600;
            ringAt(state, hub.x, hub.y, t * ring, (1 - t) * (heat > 0 ? 0.5 : 0.22), heat > 0 ? 1 : 0);
          }
          const i = cellAt(grid, hub.x, hub.y);
          if (i < 0) return;
          const pulse = 0.5 + 0.5 * Math.sin((time / 2400 + hash(n, 5)) * Math.PI * 2);
          paintMax(state, i, (heat > 0 ? 0.5 + 0.3 * pulse : 0.24) * (vignette[i] ?? 0), heat > 0 ? 1 : 0);
        });

        // Queries: land near a cluster, reach for the three nearest topics.
        if (time > nextQuery && queries.length < 2 && hubs.length > 2) {
          const from = hubs[Math.floor(Math.random() * hubs.length)];
          if (from) {
            const x = from.x + (Math.random() - 0.5) * 0.5 * grid.height;
            const y = Math.min(grid.height * 0.95, Math.max(grid.height * 0.05, from.y + (Math.random() - 0.5) * 0.4 * grid.height));
            const hits = hubs
              .map((h, n) => ({ n, d: Math.hypot(h.x - x, h.y - y) }))
              .sort((a, b) => a.d - b.d)
              .slice(0, 3)
              .map((h) => h.n);
            queries.push({ x, y, start: time, hits });
          }
          nextQuery = time + 1800 + 2200 * Math.random();
        }
        for (let q = queries.length - 1; q >= 0; q--) {
          const query = queries[q];
          if (!query) continue;
          const age = time - query.start;
          if (age > 2400) {
            queries.splice(q, 1);
            continue;
          }
          const fade = age < 1500 ? 1 : 1 - (age - 1500) / 900;
          ringAt(state, query.x, query.y, Math.min(1, age / 400) * 2.2 * grid.pitch, 0.55 * fade, 1);
          const qi = cellAt(grid, query.x, query.y);
          if (qi >= 0) paintMax(state, qi, 0.7 * fade * (vignette[qi] ?? 0), 1);
          const u = Math.min(1, Math.max(0, (age - 250) / 900));
          query.hits.forEach((n) => {
            const hub = hubs[n];
            if (!hub) return;
            line(state, query.x, query.y, hub.x, hub.y, u, 0.42 * fade);
            if (u >= 1) hot[n] = 1;
          });
        }
      },
    };
  };
}
