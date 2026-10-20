import { readFileSync } from "node:fs";
import { join } from "node:path";
import { renderToStaticMarkup } from "react-dom/server";
import { describe, expect, it } from "vitest";

import { preparedBanner, settledFrame } from "@digithings/hero-banner";
import { DIGICHAT } from "@digithings/hero-banner/definitions";

import { DigichatWordmark } from "./DigichatWordmark";
import * as React from "react";

// Test-env only: packages/hero-banner ships no tsconfig, so vitest compiles
// its web.tsx with classic JSX while production (Next.js) uses automatic.
// The free `React` name resolves here at render time.
(globalThis as unknown as Record<string, unknown>).React ??= React;

const SRC = readFileSync(join(__dirname, "DigichatWordmark.tsx"), "utf8");

/** The settled mark is the server-rendered fallback: the canvas paints on
 *  mount, so a server render and a no-JS page used to show an empty box. */
function maskPayload(html: string): string {
  const match = html.match(/mask-image:url\(&quot;(data:image\/svg\+xml,[^&]*)&quot;\)/);
  if (!match) return "";
  return decodeURIComponent(match[1].slice("data:image/svg+xml,".length));
}

/** Total width of the mask runs: the number of lit pixels the fallback shows. */
function maskLitCells(svg: string): number {
  let total = 0;
  for (const run of svg.matchAll(/M(\d+) (\d+)h(\d+)v1h-\d+z/g)) {
    total += Number(run[3]);
  }
  return total;
}

describe("DigichatWordmark", () => {
  it("draws the shared DIGICHAT definition through HeroBanner", () => {
    expect(SRC).toContain("@digithings/hero-banner/definitions");
    expect(SRC).toContain("DIGICHAT");
    expect(SRC).toContain("@digithings/hero-banner/web");
    expect(SRC).toContain("HeroBanner");
    expect(SRC).toContain("<span");
    expect(SRC).toContain("live={false}");
    expect(SRC).not.toContain("replayLoading");
    expect(SRC).not.toContain("<div");
    const html = renderToStaticMarkup(<DigichatWordmark />);
    expect(html).toContain('aria-label="digichat"');
    expect(html).toContain("<canvas");
  });

  it("keeps the shared grid off the definition, not a local copy", () => {
    const { layout } = preparedBanner(DIGICHAT);
    expect(layout.height).toBe(10);
    expect(layout.width).toBeGreaterThan(0);
    expect(SRC).not.toContain("heroWordmarkPixels");
  });

  it("shows the settled mark on the server render, not a blank canvas", () => {
    const html = renderToStaticMarkup(<DigichatWordmark />);
    // The shape travels as a mask, the colour as a CSS value the host
    // document resolves, so the fallback follows the page theme.
    expect(html).toContain("mask-image:url(");
    expect(html).toContain("mask-size:100% 100%");
    expect(html).toContain("background-color:#D7D7D7");

    const svg = maskPayload(html);
    expect(svg).toContain("<svg");
    expect(svg).toContain(`viewBox="0 0 ${preparedBanner(DIGICHAT).layout.width} 10"`);
    expect(svg).toContain('<path d="M');
    expect(svg).toContain('fill-opacity="1"');

    // The fallback must carry the whole mark: one lit pixel per lit cell.
    const frame = settledFrame(DIGICHAT);
    const lit = frame.pixels.filter((p) => p && p.alpha > 0).length;
    expect(lit).toBeGreaterThan(0);
    expect(maskLitCells(svg)).toBe(lit);
  });
});
