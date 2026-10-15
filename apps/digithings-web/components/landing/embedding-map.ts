import { cellAt, cellPoint, hash, paintMax, type FieldState, type Grid, type Subject } from "./pixel-field-core";

/**
 * The welcome hero's subject: an embedding-space map, generated fresh on every
 * load from a seed (DIG-3319).
 *
 * - land       -> clusters of a 2D-projected knowledge base: dense cores that
 *   dither out at the edges, filament strands between neighbours, stray points.
 * - hubs       -> topic centroids, one solid block per cluster, pulsing.
 * - live layer -> an index sweep drifting across the map, and queries that land,
 *   reach for their three nearest topics and leave them running hot.
 *
 * Everything structural comes from the seed, so `?seed=` reproduces a map. The
 * plan is kept apart from the canvas (`planMap`) so its guardrails are testable:
 * nothing under the headline, mass balanced left/right, fewer and smaller
 * clusters on narrow screens.
 */

export type Blob = { x: number; y: number; r: number; phase: number };
// Blob x, y and r are in height units: x runs 0..aspect, y runs 0..1.
export type Cluster = { blobs: Blob[] };

export type MapPlan = {
  clusters: Cluster[];
  /** How topics are joined: each to its nearest neighbour, or one chain through all of them. */
  strands: "nearest" | "chain";
  /** Strand bow, as a fraction of its length. */
  sag: number;
  /** Cluster drift amplitude; 0 means a still map. */
  drift: number;
  /** Chance that any empty cell shows a stray point. */
  outliers: number;
  /** Index sweep direction and period (ms). */
  sweep: { dir: 1 | -1; period: number };
  /** Hub pulse tempo multiplier. */
  tempo: number;
};

const MAX_SEED = 1_000_000;

export function mulberry32(seed: number): () => number {
  let state = seed;
  return () => {
    state = (state + 0x6d2b79f5) | 0;
    let t = Math.imul(state ^ (state >>> 15), 1 | state);
    t = (t + Math.imul(t ^ (t >>> 7), 61 | t)) ^ t;
    return ((t ^ (t >>> 14)) >>> 0) / 4294967296;
  };
}

/** `?seed=` value -> seed. Digits are used as-is; any other text is hashed, so `?seed=launch` works too. */
export function parseSeed(raw: string | null | undefined): number | null {
  const text = raw?.trim();
  if (!text) return null;
  if (/^\d{1,9}$/.test(text)) return Number(text);
  let h = 0x811c9dc5;
  for (let i = 0; i < text.length; i++) h = Math.imul(h ^ text.charCodeAt(i), 0x01000193);
  return (h >>> 0) % MAX_SEED;
}

export function randomSeed(): number {
  const n = new Uint32Array(1);
  crypto.getRandomValues(n);
  return (n[0] ?? 0) % MAX_SEED;
}

/**
 * The headline's keep-out, the same ellipse the vignette clears (x in width
 * fractions, y in height fractions). Returns the normalised distance: < 1 is
 * inside it.
 */
export function headlineDistance(x: number, y: number, small: boolean): number {
  return Math.hypot((x - 0.5) / (small ? 0.62 : 0.34), (y - 0.46) / 0.5);
}

/** No blob may reach inside this normalised radius: that is where the text sits. */
export const HEADLINE_CORE = 0.62;

/** Distance of a blob's nearest edge from the headline centre, in the same units. */
export function blobClearance(blob: Blob, aspect: number, small: boolean): number {
  return headlineDistance(blob.x / aspect, blob.y, small) - blob.r / 0.5;
}

/** Share of land mass on the left half. Balanced maps sit near 0.5. */
export function leftShare(clusters: Cluster[], aspect: number): number {
  let left = 0;
  let total = 0;
  for (const c of clusters) {
    for (const b of c.blobs) {
      const m = b.r * b.r;
      total += m;
      if (b.x < aspect / 2) left += m;
    }
  }
  return total ? left / total : 0.5;
}

type Spec = { x: number; y: number; size: number; stretch: number; angle: number; parts: number };

function walk(spec: Spec, aspect: number, rand: () => number): Blob[] {
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
  return blobs;
}

function draft(rand: () => number, aspect: number, small: boolean): Cluster[] {
  // Narrow screens get fewer, smaller clusters; the keep-out covers most of the width there.
  const major = small ? 3 + Math.floor(3 * rand()) : 4 + Math.floor(5 * rand());
  const islands = small ? Math.floor(3 * rand()) : 1 + Math.floor(4 * rand());
  const scale = small ? 0.5 : 0.8 + 0.4 * rand();
  // Some maps hug the frame edge, some spread further in.
  const edgeBias = rand();
  const specs: Spec[] = [];
  for (let tries = 0; specs.length < major + islands && tries < 400; tries++) {
    const island = specs.length >= major;
    const size = scale * (island ? 0.05 + 0.05 * rand() : 0.12 + 0.2 * rand());
    let x = rand();
    if (rand() < edgeBias) x = x < 0.5 ? x * x * 2 * 0.5 : 1 - (1 - x) * (1 - x) * 2 * 0.5;
    const y = 0.04 + 0.92 * rand();
    if (headlineDistance(x, y, small) < 0.8 + 1.2 * size) continue;
    if (specs.some((s) => Math.hypot((s.x - x) * aspect, s.y - y) < (s.size + size) * 0.95)) continue;
    specs.push({
      x,
      y,
      size,
      stretch: 1 + rand(),
      angle: Math.PI * rand(),
      parts: island ? 1 + Math.floor(2 * rand()) : 3 + Math.floor(5 * rand()),
    });
  }
  return specs.map((spec) => ({
    // Drop any blob the random walk carried into the headline.
    blobs: walk(spec, aspect, rand).filter((b) => blobClearance(b, aspect, small) >= HEADLINE_CORE),
  })).filter((c) => c.blobs.length > 0);
}

/** Deterministic map plan for a seed and frame shape. Retries drafts until the guardrails hold. */
export function planMap(seed: number, aspect: number, small: boolean): MapPlan {
  const rand = mulberry32(seed);
  let best: Cluster[] = [];
  let bestScore = Infinity;
  for (let attempt = 0; attempt < 16; attempt++) {
    const clusters = draft(rand, aspect, small);
    const share = leftShare(clusters, aspect);
    const score = Math.abs(share - 0.5) + (clusters.length < 3 ? 1 : 0);
    if (score < bestScore) {
      best = clusters;
      bestScore = score;
    }
    if (score <= 0.15) break;
  }
  return {
    clusters: best,
    strands: rand() < 0.6 ? "nearest" : "chain",
    sag: 0.04 + 0.16 * rand(),
    drift: rand() < 0.4 ? 0 : 0.2 + 0.4 * rand(),
    outliers: 0.003 + 0.011 * rand(),
    sweep: { dir: rand() < 0.5 ? 1 : -1, period: 32000 + 18000 * rand() },
    tempo: 0.7 + 0.6 * rand(),
  };
}

function smooth(a: number, b: number, v: number): number {
  const t = Math.min(1, Math.max(0, (v - a) / (b - a)));
  return t * t * (3 - 2 * t);
}

type Point = { x: number; y: number };
type Query = Point & { start: number; hits: number[] };

/** Pairs of hub indices the filament strands run between. */
function strandPairs(hubs: Point[], mode: MapPlan["strands"]): [number, number][] {
  const near = (from: number, skip: (m: number) => boolean) => {
    let best = -1;
    let bestD = Infinity;
    hubs.forEach((b, m) => {
      const a = hubs[from];
      if (!a || m === from || skip(m)) return;
      const d = Math.hypot(b.x - a.x, b.y - a.y);
      if (d < bestD) {
        bestD = d;
        best = m;
      }
    });
    return best;
  };
  if (mode === "nearest") {
    return hubs.map((_, n) => [n, near(n, () => false)] as [number, number]).filter(([, m]) => m >= 0);
  }
  // Greedy nearest-neighbour chain from the leftmost topic: one long filament through the map.
  const pairs: [number, number][] = [];
  const used = new Set<number>();
  let at = hubs.reduce((lo, h, n) => (h.x < (hubs[lo]?.x ?? Infinity) ? n : lo), 0);
  used.add(at);
  while (used.size < hubs.length) {
    const next = near(at, (m) => used.has(m));
    if (next < 0) break;
    pairs.push([at, next]);
    used.add(next);
    at = next;
  }
  return pairs;
}

export function createEmbeddingSubject(seed: number): (grid: Grid) => Subject {
  return (grid) => {
    const count = grid.cols * grid.rows;
    const aspect = grid.width / grid.height;
    const plan = planMap(seed, aspect, grid.small);
    const rand = mulberry32(seed ^ 0x9e3779b9);

    // Same centre clearing as the keep-out, so the headline stays readable.
    const vignette = new Float32Array(count);
    const ux = new Float32Array(count);
    const uy = new Float32Array(count);
    for (let i = 0; i < count; i++) {
      const p = cellPoint(grid, i);
      const d = headlineDistance(p.x / grid.width, p.y / grid.height, grid.small);
      vignette[i] = 0.08 + 0.92 * smooth(0.7, 1.25, d);
      ux[i] = p.x / grid.height;
      uy[i] = p.y / grid.height;
    }

    const blobAt = (blob: Blob, time: number) =>
      plan.drift
        ? {
            x: blob.x + Math.sin(time / 9000 + blob.phase) * blob.r * plan.drift,
            y: blob.y + Math.cos(time / 11000 + blob.phase * 1.3) * blob.r * plan.drift * 0.75,
            r: blob.r * (0.92 + 0.1 * Math.sin(time / 7000 + blob.phase)),
          }
        : blob;

    const density = new Float32Array(count);
    const hubs: Point[] = plan.clusters.map(() => ({ x: 0, y: 0 }));
    let densityAt = -Infinity;
    function refresh(time: number) {
      densityAt = time;
      const placed = plan.clusters.map((c) => c.blobs.map((b) => blobAt(b, time)));
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
        density[i] = 0.82 * smooth(0.22, 1.1, d) + plan.outliers;
      }
      // Filaments: thin strands of points between topics, like the bridges a
      // UMAP projection leaves between clusters.
      for (const [n, m] of strandPairs(hubs, plan.strands)) {
        const a = hubs[n];
        const b = hubs[m];
        if (!a || !b) continue;
        const len = Math.hypot(b.x - a.x, b.y - a.y);
        if (!len) continue;
        const steps = Math.ceil(len / grid.pitch);
        for (let s = 0; s <= steps; s++) {
          const f = s / steps;
          const sag = Math.sin(f * Math.PI) * plan.sag * len;
          const i = cellAt(grid, a.x + (b.x - a.x) * f - ((b.y - a.y) / len) * sag, a.y + (b.y - a.y) * f + ((b.x - a.x) / len) * sag);
          if (i >= 0) density[i] = Math.max(density[i] ?? 0, 0.55);
        }
      }
    }
    refresh(0);

    // Seeded, so the first frame of a given ?seed= is identical every time.
    const lit = new Uint8Array(count);
    const flicker = new Float32Array(count);
    for (let i = 0; i < count; i++) {
      lit[i] = rand() < (density[i] ?? 0) ? 1 : 0;
      flicker[i] = 0.6 + 0.4 * rand();
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
        if (plan.drift && time - densityAt > 300) refresh(time);

        const flips = Math.max(1, Math.round(0.006 * count));
        for (let n = 0; n < flips; n++) {
          const i = Math.floor(Math.random() * count);
          lit[i] = Math.random() < (density[i] ?? 0) ? 1 : 0;
        }

        // Index sweep: a soft band crossing the map, direction and pace per seed.
        const along = ((time / plan.sweep.period) % 1.3) - 0.15;
        const sweep = (plan.sweep.dir > 0 ? along : 1 - along) * grid.width;
        const band = 0.13 * grid.width;
        for (let i = 0; i < count; i++) {
          state.kind[i] = 0;
          if (!lit[i]) {
            // Faint dot grid under the whole map: the empty space of the projection.
            state.target[i] = 0.011 * (vignette[i] ?? 0);
            continue;
          }
          const off = ((ux[i] ?? 0) * grid.height - sweep) / band;
          const fresh = 0.82 + 0.5 * Math.exp(-off * off);
          state.target[i] = 0.15 * fresh * (flicker[i] ?? 1) * (vignette[i] ?? 0);
        }

        for (let n = 0; n < hot.length; n++) hot[n] = Math.max(0, (hot[n] ?? 0) - dt / 4500);

        hubs.forEach((hub, n) => {
          const heat = hot[n] ?? 0;
          const period = (3600 + 3800 * hash(n, seed)) * plan.tempo;
          const phase = (time + 6000 * hash(n, seed + 3)) % period;
          if (phase < 1600) {
            const t = phase / 1600;
            ringAt(state, hub.x, hub.y, t * ring, (1 - t) * (heat > 0 ? 0.5 : 0.22), heat > 0 ? 1 : 0);
          }
          const center = cellAt(grid, hub.x, hub.y);
          if (center < 0) return;
          // Topic centroid: a solid 3x3 block.
          const pulse = 0.5 + 0.5 * Math.sin((time / (2400 * plan.tempo) + hash(n, seed + 5)) * Math.PI * 2);
          const alpha = heat > 0 ? 0.6 + 0.3 * pulse : 0.34 + 0.08 * pulse;
          const col = center % grid.cols;
          const row = (center - col) / grid.cols;
          for (let dy = -1; dy <= 1; dy++) {
            for (let dx = -1; dx <= 1; dx++) {
              const c = col + dx;
              const r = row + dy;
              if (c < 0 || r < 0 || c >= grid.cols || r >= grid.rows) continue;
              const i = r * grid.cols + c;
              paintMax(state, i, alpha * (vignette[i] ?? 0), heat > 0 ? 1 : 0);
            }
          }
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
