import { type FieldState, type Grid, type Subject } from "./pixel-field-core";

/**
 * Concept 3 — glass rings. Nested square frames expand outward from
 * center, one inside the next, echoing the hero's own headline ("a glass
 * box you own"). Pure geometry, no bitmap, no hubs — just Chebyshev rings
 * on the grid pulsing outward on a loop.
 */

export function createGlassRingsSubject(grid: Grid): Subject {
  const cx = (grid.cols - 1) / 2;
  const cy = (grid.rows - 1) / 2;
  const maxRing = Math.max(grid.cols, grid.rows) / 2;
  const ringOf = new Float32Array(grid.cols * grid.rows);
  for (let row = 0; row < grid.rows; row++) {
    for (let col = 0; col < grid.cols; col++) {
      ringOf[row * grid.cols + col] = Math.max(Math.abs(col - cx), Math.abs(row - cy));
    }
  }
  const period = 5200;
  const bandWidth = 1.6;

  return {
    update(time: number, state: FieldState) {
      const phase = (time % period) / period;
      const frontier = phase * maxRing * 1.15;
      for (let i = 0; i < ringOf.length; i++) {
        const ring = ringOf[i] ?? 0;
        const d = frontier - ring;
        let alpha = 0;
        if (d >= 0 && d < bandWidth) {
          alpha = 0.55 * (1 - d / bandWidth);
        }
        // A second, faster frontier keeps the field from ever reading empty
        // between loops of the slow one.
        const fast = ((phase + 0.5) % 1) * maxRing * 1.15;
        const d2 = fast - ring;
        if (d2 >= 0 && d2 < bandWidth) {
          alpha = Math.max(alpha, 0.3 * (1 - d2 / bandWidth));
        }
        state.target[i] = alpha;
        state.kind[i] = ring < maxRing * 0.08 ? 1 : 0;
      }
    },
  };
}
