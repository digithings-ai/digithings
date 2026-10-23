import { createEmbeddingSubject } from "../../components/landing/embedding-map";

/**
 * The landing page's embedding field, rendered as a static SVG run.
 *
 * The same function is used by the server-rendered fallback PDF and by the
 * browser download builder, so a generated edition and a downloaded edition
 * cannot drift apart. The grid is portrait A4 and deliberately has no
 * headline keep-out: in print the empty ellipse read as a cutout.
 */
export const FIELD_COLS = 84;
export const FIELD_ROWS = 118;

export function fieldSvg({
  seed,
  time,
  strength = 1.6,
  cols = FIELD_COLS,
  rows = FIELD_ROWS,
}: {
  seed: number;
  time: number;
  strength?: number;
  cols?: number;
  rows?: number;
}): string {
  const count = cols * rows;
  const state = { target: new Float32Array(count), kind: new Uint8Array(count) };
  const grid = {
    cols,
    rows,
    pitch: 10,
    width: cols * 10,
    height: rows * 10,
    offsetX: 0,
    offsetY: 0,
    small: false,
  };
  createEmbeddingSubject(seed, { keepOut: false })(grid).update(time, state);
  const runs: string[] = [];
  for (let y = 0; y < rows; y += 1) {
    let x = 0;
    while (x < cols) {
      const index = y * cols + x;
      const alpha = state.target[index] ?? 0;
      if (alpha < 0.015) {
        x += 1;
        continue;
      }
      const kind = state.kind[index] === 1 ? "--accent" : "--ink";
      const shade = Math.min(1, Math.round(alpha * strength * 100) / 100);
      let width = 1;
      while (x + width < cols) {
        const next = y * cols + x + width;
        const nextShade = Math.min(1, Math.round((state.target[next] ?? 0) * strength * 100) / 100);
        if ((state.kind[next] === 1 ? "--accent" : "--ink") !== kind || nextShade !== shade) break;
        width += 1;
      }
      runs.push(
        `<rect x="${x}" y="${y}" width="${(width * 0.78).toFixed(2)}" height="0.78" fill="var(${kind})" fill-opacity="${shade.toFixed(2)}"/>`,
      );
      x += width;
    }
  }
  return `<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 ${cols} ${rows}" preserveAspectRatio="none" shape-rendering="crispEdges" aria-hidden="true">${runs.join("")}</svg>`;
}
