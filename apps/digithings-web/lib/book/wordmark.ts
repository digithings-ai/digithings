import { sampleBanner, type Frame } from "@digithings/hero-banner";
import { DIGITHINGS } from "@digithings/hero-banner/definitions";

/** An actual build-animation frame, as a print-safe SVG. */
function frameSvg(frame: Frame): string {
  const runs: string[] = [];
  for (let y = 0; y < frame.height; y += 1) {
    let x = 0;
    while (x < frame.width) {
      const pixel = frame.pixels[y * frame.width + x];
      if (!pixel || pixel.alpha <= 0) {
        x += 1;
        continue;
      }
      const tone = pixel.tone === "accent" ? "--accent" : "--ink";
      const alpha = Math.min(1, pixel.alpha);
      let width = 1;
      while (x + width < frame.width) {
        const next = frame.pixels[y * frame.width + x + width];
        if (!next || next.tone !== pixel.tone || Math.min(1, next.alpha) !== alpha) break;
        width += 1;
      }
      runs.push(
        `<rect x="${x}" y="${y}" width="${width}" height="1" fill="var(${tone})" fill-opacity="${alpha.toFixed(2)}"/>`,
      );
      x += width;
    }
  }
  return `<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 ${frame.width} ${frame.height}" preserveAspectRatio="xMidYMid meet" shape-rendering="crispEdges" aria-hidden="true">${runs.join("")}</svg>`;
}

/** Mid-build frame from the same script the landing hero runs. */
export const WORDMARK = frameSvg(sampleBanner(DIGITHINGS, { t: 940 }).frame);
