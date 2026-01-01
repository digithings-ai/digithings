import { describe, expect, it } from "bun:test";

import { BANNERS, DIGICHAT, DIGIQUANT, DIGITHINGS } from "../src/definitions";
import { settledFallback, settledFrame, settledSvg } from "../src/ssr";

/** The payload of a `url("data:image/svg+xml,…")` value, decoded. */
function payloadOf(url: string): string {
  const match = /^url\("data:image\/svg\+xml,(.*)"\)$/.exec(url);
  if (!match) throw new Error(`not a data uri: ${url.slice(0, 48)}`);
  return decodeURIComponent(match[1] as string);
}

/** Every horizontal run in the SVG path data. */
function runsOf(svg: string): { x: number; y: number; w: number }[] {
  const runs: { x: number; y: number; w: number }[] = [];
  for (const path of svg.matchAll(/<path d="([^"]*)"/g)) {
    for (const run of (path[1] as string).matchAll(/M(\d+) (\d+)h(\d+)v1h-\d+z/g)) {
      runs.push({ x: Number(run[1]), y: Number(run[2]), w: Number(run[3]) });
    }
  }
  return runs;
}

function litCells(frame: { pixels: ({ alpha: number } | null)[] }): number {
  return frame.pixels.filter((pixel) => pixel && pixel.alpha > 0).length;
}

describe("settled mark", () => {
  it("settles to the same frame every time", () => {
    const first = JSON.stringify(settledFrame(DIGIQUANT));
    const second = JSON.stringify(settledFrame(DIGIQUANT));
    expect(first).toBe(second);
    expect(litCells(settledFrame(DIGIQUANT))).toBeGreaterThan(0);
  });

  it("covers exactly the lit cells of the settled frame", () => {
    for (const def of [DIGITHINGS, DIGIQUANT, DIGICHAT]) {
      const frame = settledFrame(def);
      const runs = runsOf(settledSvg(def));
      const covered = runs.reduce((sum, run) => sum + run.w, 0);
      expect(covered).toBe(litCells(frame));
      for (const run of runs) {
        expect(run.x + run.w).toBeLessThanOrEqual(frame.width);
        expect(run.y).toBeLessThan(frame.height);
      }
    }
  });

  it("keeps every cell inside the frame", () => {
    const frame = settledFrame(DIGITHINGS);
    const runs = runsOf(settledSvg(DIGITHINGS));
    expect(runs.length).toBeGreaterThan(0);
    for (const run of runs) expect(run.y).toBeLessThan(frame.height);
  });

  it("keeps the alpha levels of the settled frame", () => {
    const alphas = [...settledSvg(DIGITHINGS).matchAll(/fill-opacity="([0-9.]+)"/g)].map((m) => Number(m[1]));
    expect(alphas.length).toBeGreaterThan(1);
    expect(alphas).toContain(1);
  });

  it("paints a themed mark with the theme variable and a fixed tone with its hex", () => {
    expect(settledFallback(DIGIQUANT).color).toBe("var(--ink)");
    expect(settledFallback(DIGICHAT).color).toBe("#D7D7D7");
  });

  it("settles every definition to a single colour, so the mask carries the shape", () => {
    for (const [name, def] of Object.entries(BANNERS)) {
      const fallback = settledFallback(def);
      expect(`${name}:${fallback.kind}`).toBe(`${name}:mask`);
      expect(fallback.multiTone).toBe(false);
    }
  });

  it("encodes a data uri the browser can read", () => {
    const url = settledFallback(DIGIQUANT).url;
    expect(url.startsWith('url("data:image/svg+xml,')).toBe(true);
    expect(url.endsWith('")')).toBe(true);
    const encoded = /^url\("data:image\/svg\+xml,(.*)"\)$/.exec(url)?.[1] as string;
    expect(encoded).toBeTruthy();
    expect(encoded).not.toContain('"');
    expect(encoded).not.toContain("<");
    expect(encoded).not.toContain(">");
    expect(encoded).not.toContain("'");
    expect(encoded).not.toContain("(");
    const payload = payloadOf(url);
    expect(payload).toContain("<svg");
    expect(payload).toContain("viewBox=");
  });
});
