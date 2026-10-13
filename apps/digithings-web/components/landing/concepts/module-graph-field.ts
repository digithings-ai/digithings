import { cellAt, cellPoint, hash, paintMax, type FieldState, type Grid, type Subject } from "./pixel-field-core";

/**
 * Concept 1 — module graph. Nine fixed nodes (one per digi module) linked by
 * the edges modules actually share data over, with pulses that travel those
 * edges to read as live data flow. Direct reskin of the production file's
 * hub/pulse/arc mechanics: hubs become module nodes, arcs become flow along
 * a *fixed* adjacency instead of a random city pair.
 */

const MODULES = [
  { x: 0.5, y: 0.18 }, // digikey — identity sits central, up top
  { x: 0.22, y: 0.32 },
  { x: 0.78, y: 0.32 },
  { x: 0.12, y: 0.58 },
  { x: 0.5, y: 0.5 }, // digistore — hub of the graph
  { x: 0.88, y: 0.58 },
  { x: 0.3, y: 0.8 },
  { x: 0.7, y: 0.8 },
  { x: 0.5, y: 0.92 },
] as const;

const EDGES: [number, number][] = [
  [0, 4], [1, 4], [2, 4], [3, 4], [5, 4], [6, 4], [7, 4], [8, 4],
  [0, 1], [0, 2], [1, 3], [2, 5], [6, 8], [7, 8],
];

export function createModuleGraphSubject(grid: Grid): Subject {
  const cx = grid.width / 2;
  const cy = grid.height / 2;
  const span = Math.min(grid.width, grid.height * 1.3);
  const nodes = MODULES.map((node, index) => ({
    point: {
      x: cx + (node.x - 0.5) * span,
      y: cy + (node.y - 0.5) * span * (grid.height / Math.max(grid.height, span)),
    },
    period: 2600 + 2600 * hash(index, 11),
    phase: 6000 * hash(index, 5),
  }));
  const ring = Math.max(36, 5 * grid.pitch);
  const arcs: { from: number; to: number; start: number; duration: number }[] = [];
  let nextArc = 1200;

  return {
    update(time: number, state: FieldState) {
      for (let i = 0; i < state.target.length; i++) {
        state.target[i] = 0;
        state.kind[i] = 0;
      }

      // Idle links: a faint always-on line between every connected pair, so
      // the graph reads as a structure even before any pulse travels it.
      for (const [from, to] of EDGES) {
        const a = nodes[from]?.point;
        const b = nodes[to]?.point;
        if (!a || !b) continue;
        const steps = 24;
        for (let step = 0; step <= steps; step++) {
          const u = step / steps;
          const x = a.x + (b.x - a.x) * u;
          const y = a.y + (b.y - a.y) * u;
          const i = cellAt(grid, x, y);
          paintMax(state, i, 0.05, 0);
        }
      }

      const reach = Math.ceil(ring / grid.pitch) + 1;
      nodes.forEach((node, index) => {
        const phase = (time + node.phase) % node.period;
        const pulse = 0.5 + 0.5 * Math.sin(((time + node.phase) / 2200) * Math.PI * 2);
        const center = cellAt(grid, node.point.x, node.point.y);
        paintMax(state, center, 0.35 + 0.35 * pulse, index === 4 ? 1 : 0);
        if (phase > 1500) return;
        const t = phase / 1500;
        const radius = t * ring;
        const alpha = (1 - t) * 0.4;
        const col = Math.floor((node.point.x - grid.offsetX) / grid.pitch);
        const row = Math.floor((node.point.y - grid.offsetY) / grid.pitch);
        for (let dy = -reach; dy <= reach; dy++) {
          for (let dx = -reach; dx <= reach; dx++) {
            const c = col + dx;
            const r = row + dy;
            if (c < 0 || r < 0 || c >= grid.cols || r >= grid.rows) continue;
            const i = r * grid.cols + c;
            const p = cellPoint(grid, i);
            if (Math.abs(Math.hypot(p.x - node.point.x, p.y - node.point.y) - radius) > 0.6 * grid.pitch) continue;
            paintMax(state, i, alpha, index === 4 ? 1 : 0);
          }
        }
      });

      if (time > nextArc && arcs.length < 2) {
        const [from, to] = EDGES[Math.floor(Math.random() * EDGES.length)] ?? [0, 4];
        const a = nodes[from]?.point;
        const b = nodes[to]?.point;
        if (a && b) {
          const dist = Math.hypot(b.x - a.x, b.y - a.y);
          arcs.push({ from, to, start: time, duration: 700 + 2.2 * dist });
        }
        nextArc = time + 900 + 1400 * Math.random();
      }
      for (let n = arcs.length - 1; n >= 0; n--) {
        const arc = arcs[n];
        const a = nodes[arc.from]?.point;
        const b = nodes[arc.to]?.point;
        if (!a || !b) {
          arcs.splice(n, 1);
          continue;
        }
        const t = (time - arc.start) / arc.duration;
        if (t > 1.2) {
          arcs.splice(n, 1);
          continue;
        }
        for (let step = 0; step < 6; step++) {
          const u = Math.min(1, t - 0.04 * step);
          if (u < 0) continue;
          const x = a.x + (b.x - a.x) * u;
          const y = a.y + (b.y - a.y) * u;
          const i = cellAt(grid, x, y);
          paintMax(state, i, 0.6 * (1 - step / 6), 1);
        }
      }
    },
  };
}
