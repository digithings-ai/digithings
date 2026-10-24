/**
 * Renderer agreement: the canvas, the half-block terminal encoder and the SVG
 * mask that the server and no-JS page paint must mark exactly the same cells
 * as the frame the engine samples. No pixels are compared; only which cells
 * are lit.
 */
import { describe, expect, test } from "bun:test";

import { paintFrame } from "../src/canvas";
import { BANNERS, DIGIVOICE_BASELINE as DIGIVOICE } from "../src/definitions";
import { sampleBanner } from "../src/engine";
import { settledFrame, settledSvg } from "../src/ssr";
import { halfBlocks } from "../src/tui";
import type { BannerDefinition, Frame } from "../src/types";

const DEFS: [string, BannerDefinition][] = [...Object.entries(BANNERS), ["digivoice-baseline", DIGIVOICE]];
const LIT = (frame: Frame, x: number, y: number) => (frame.pixels[y * frame.width + x]?.alpha ?? 0) > 0;

/** Row-major `#`/`.` map of the cells a renderer marks. */
function map(width: number, height: number, lit: (x: number, y: number) => boolean): string {
  let out = "";
  for (let y = 0; y < height; y += 1) for (let x = 0; x < width; x += 1) out += lit(x, y) ? "#" : ".";
  return out;
}

const frameMap = (frame: Frame) => map(frame.width, frame.height, (x, y) => LIT(frame, x, y));

/** The cells the canvas renderer fills, recorded from its draw calls. */
function canvasMap(frame: Frame): string {
  const filled = new Set<string>();
  const ctx = {
    fillStyle: "",
    globalAlpha: 1,
    clearRect() {},
    fillRect(x: number, y: number, w: number, h: number) {
      for (let dy = 0; dy < h; dy += 1) for (let dx = 0; dx < w; dx += 1) filled.add(`${x + dx},${y + dy}`);
    },
  };
  paintFrame(ctx, frame, { pixel: 1, colors: {} });
  return map(frame.width, frame.height, (x, y) => filled.has(`${x},${y}`));
}

/** The cells the terminal encoder covers: `█` is both halves and `▀` is the top
 *  plus the bottom when it also carries a `bg`; `▄` is the bottom alone. */
function halfBlockMap(frame: Frame, def: BannerDefinition): string {
  const cells = halfBlocks(frame, def.palette, "truecolor");
  return map(frame.width, frame.height, (x, y) => {
    const cell = cells[Math.floor(y / 2)]?.[x];
    if (!cell) return false;
    if (cell.ch === "█" || (cell.ch === "▀" && cell.bg)) return true;
    if (cell.ch === "▀") return y % 2 === 0;
    if (cell.ch === "▄") return y % 2 === 1;
    return false;
  });
}

/** The cells the settled SVG covers, read back from its path data. */
function svgMap(def: BannerDefinition, frame: Frame): string {
  const runs: { x: number; y: number; w: number }[] = [];
  for (const path of settledSvg(def).matchAll(/<path d="([^"]*)"/g)) {
    for (const run of (path[1] as string).matchAll(/M(\d+) (\d+)h(\d+)v1h-\d+z/g)) {
      runs.push({ x: Number(run[1]), y: Number(run[2]), w: Number(run[3]) });
    }
  }
  return map(frame.width, frame.height, (x, y) =>
    runs.some((run) => run.y === y && x >= run.x && x < run.x + run.w),
  );
}

describe("the three renderers agree", () => {
  for (const [name, def] of DEFS) {
    test(`${name}: canvas fills exactly the lit cells`, () => {
      for (const t of [0, 200, 900, 1900, 5000]) {
        const frame = sampleBanner(def, { t, live: true }).frame;
        expect(`${name}@${t}`).not.toBe("");
        expect(canvasMap(frame)).toBe(frameMap(frame));
      }
    });

    test(`${name}: half-blocks cover exactly the lit cells`, () => {
      for (const t of [0, 200, 900, 1900, 5000]) {
        const frame = sampleBanner(def, { t, live: true }).frame;
        expect(halfBlockMap(frame, def)).toBe(frameMap(frame));
      }
    });

    test(`${name}: the settled SVG mask covers exactly the settled frame`, () => {
      const frame = settledFrame(def);
      expect(svgMap(def, frame)).toBe(frameMap(frame));
    });

    test(`${name}: reduced motion is that same settled frame at every moment`, () => {
      const settled = frameMap(settledFrame(def));
      for (const t of [0, 200, 900, 5000]) {
        expect(frameMap(sampleBanner(def, { t, motion: "reduced" }).frame)).toBe(settled);
      }
    });
  }
});
