import { hash, paintMax, type FieldState, type Grid, type Subject } from "./pixel-field-core";

/**
 * Concept 2 — circuit traces. Replaces the land bitmap with a geometric
 * rail mask (orthogonal traces + vias, PCB-style) so there's no literal
 * map underneath. Signal dots travel the rails to read as "a traced
 * request path" — the phrase already in the hero copy.
 */

type Rail = { axis: "row" | "col"; index: number; from: number; to: number };

export function createCircuitSubject(grid: Grid): Subject {
  const rowStep = grid.small ? 5 : 7;
  const colStep = grid.small ? 6 : 9;
  const isRail = new Uint8Array(grid.cols * grid.rows);
  const rails: Rail[] = [];

  for (let row = 0; row < grid.rows; row += rowStep) {
    const from = Math.floor(hash(row, 1) * grid.cols * 0.3);
    const to = grid.cols - 1 - Math.floor(hash(row, 2) * grid.cols * 0.3);
    if (to <= from) continue;
    rails.push({ axis: "row", index: row, from, to });
    for (let col = from; col <= to; col++) isRail[row * grid.cols + col] = 1;
  }
  for (let col = 0; col < grid.cols; col += colStep) {
    const from = Math.floor(hash(col, 3) * grid.rows * 0.3);
    const to = grid.rows - 1 - Math.floor(hash(col, 4) * grid.rows * 0.3);
    if (to <= from) continue;
    rails.push({ axis: "col", index: col, from, to });
    for (let row = from; row <= to; row++) isRail[row * grid.cols + col] = 1;
  }

  const vignette = new Float32Array(grid.cols * grid.rows);
  const cx = grid.width / 2;
  const cy = grid.height * 0.5;
  for (let i = 0; i < vignette.length; i++) {
    const col = i % grid.cols;
    const row = (i - col) / grid.cols;
    const dx = (col * grid.pitch + grid.offsetX - cx) / (grid.width / 2);
    const dy = (row * grid.pitch + grid.offsetY - cy) / (grid.height / 2);
    const d = Math.min(1, Math.hypot(dx, dy));
    vignette[i] = 0.25 + 0.75 * (1 - d * d);
  }

  const signals = rails.map((rail, index) => ({
    rail,
    period: 2200 + 2600 * hash(index, 13),
    phase: 5000 * hash(index, 7),
  }));

  return {
    update(time: number, state: FieldState) {
      for (let i = 0; i < isRail.length; i++) {
        state.kind[i] = 0;
        state.target[i] = isRail[i] ? 0.07 * (vignette[i] ?? 0) : 0;
      }
      // Vias: every rail intersection pulses faintly, like a solder point.
      for (const rail of rails) {
        if (rail.axis !== "row") continue;
        for (const other of rails) {
          if (other.axis !== "col" || other.index < rail.from || other.index > rail.to) continue;
          if (rail.index < other.from || rail.index > other.to) continue;
          const i = rail.index * grid.cols + other.index;
          paintMax(state, i, 0.22 * (vignette[i] ?? 0), 0);
        }
      }
      signals.forEach((signal) => {
        const phase = (time + signal.phase) % signal.period;
        const t = phase / signal.period;
        const { rail } = signal;
        const length = rail.to - rail.from;
        if (length <= 0) return;
        const pos = rail.from + t * length;
        for (let spread = -2; spread <= 2; spread++) {
          const p = Math.round(pos) + spread;
          if (p < rail.from || p > rail.to) continue;
          const i = rail.axis === "row" ? rail.index * grid.cols + p : p * grid.cols + rail.index;
          const alpha = 0.75 * (1 - Math.abs(spread) / 3);
          paintMax(state, i, alpha * (vignette[i] ?? 0), 1);
        }
      });
    },
  };
}
