/**
 * Static frames of the digichat dot-matrix glyphs (the same cube coordinates
 * as `DotMatrix`). Replay files inline the svg so they do not fetch an icon.
 */

type Cell = readonly [number, number];

const GLYPHS = {
  user: [
    [1, 1],
    [2, 2],
    [3, 1],
  ],
  example: [
    [1, 2],
    [2, 1],
    [2, 3],
    [3, 2],
  ],
  expand: [
    [1, 2],
    [2, 3],
    [3, 2],
  ],
  success: [
    [1, 4],
    [2, 3],
    [3, 0],
    [3, 2],
    [4, 1],
  ],
  error: [
    [0, 0],
    [0, 4],
    [1, 1],
    [1, 3],
    [2, 2],
    [3, 1],
    [3, 3],
    [4, 0],
    [4, 4],
  ],
  idle: [
    [0, 0],
    [0, 4],
    [4, 0],
    [4, 4],
  ],
} as const satisfies Record<string, readonly Cell[]>;

export type ReplayGlyph = keyof typeof GLYPHS;

export function dotMatrix(
  state: ReplayGlyph,
  options: { decorative?: boolean; label?: string } = {},
): string {
  const rects = GLYPHS[state]
    .map(([row, col]) => {
      const x = (0.85 + col * 4).toFixed(2);
      const y = (0.85 + row * 4).toFixed(2);
      return `<rect data-slot="dot-matrix-dot" data-on="true" x="${x}" y="${y}" width="2.3" height="2.3" fill="currentColor" shape-rendering="crispEdges"></rect>`;
    })
    .join("");
  const name = options.decorative
    ? ` aria-hidden="true"`
    : ` role="img" aria-label="${escapeAttr(options.label ?? state)}"`;
  return `<span data-slot="dot-matrix" data-state="${state}"${name} class="replay-matrix"><svg data-slot="dot-matrix-grid" aria-hidden="true" viewBox="0 0 20 20" width="100%" height="100%" fill="currentColor">${rects}</svg></span>`;
}

export function disclosureChevron(): string {
  return `<span data-slot="disclosure-chevron" class="aui-disclosure-chevron">${dotMatrix("expand", { decorative: true })}</span>`;
}

function escapeAttr(value: string): string {
  return value.replace(/&/g, "&amp;").replace(/"/g, "&quot;").replace(/</g, "&lt;");
}
