import type { Frame, Palette } from "./types";

/**
 * Web renderer core: paint a frame on a 2D canvas, one square per pixel.
 * Tones with a `cssVar` follow the page theme through `resolve`; the rest use
 * their hex. Alpha is canvas alpha, so the page ground shows through, as the
 * SVG marks did with opacity.
 */

export type Canvas2D = Pick<CanvasRenderingContext2D, "clearRect" | "fillRect"> & {
  fillStyle: string | CanvasGradient | CanvasPattern;
  globalAlpha: number;
};

export function toneColors(palette: Palette, resolve?: (cssVar: string) => string | null): Record<string, string> {
  const out: Record<string, string> = {};
  for (const [name, tone] of Object.entries(palette)) {
    const themed = tone.cssVar && resolve ? resolve(tone.cssVar)?.trim() : null;
    out[name] = themed || tone.hex;
  }
  return out;
}

export function paintFrame(
  ctx: Canvas2D,
  frame: Frame,
  { pixel, colors }: { pixel: number; colors: Record<string, string> },
): void {
  ctx.clearRect(0, 0, frame.width * pixel, frame.height * pixel);
  for (let y = 0; y < frame.height; y += 1) {
    for (let x = 0; x < frame.width; x += 1) {
      const p = frame.pixels[y * frame.width + x];
      if (!p || p.alpha <= 0) continue;
      ctx.globalAlpha = Math.min(1, p.alpha);
      ctx.fillStyle = colors[p.tone] ?? colors.ink ?? "#ffffff"; // canon-allow: canvas fallback outside the DOM cascade; the definition palette is the sanctioned source
      ctx.fillRect(x * pixel, y * pixel, pixel, pixel);
    }
  }
  ctx.globalAlpha = 1;
}
