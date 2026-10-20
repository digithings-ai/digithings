import * as React from "react";
import { createElement } from "react";
import { renderToStaticMarkup } from "react-dom/server";

// Test-env only: packages/hero-banner ships no tsconfig, so vitest compiles
// its web.tsx with classic JSX while production (Next.js) uses automatic.
// The free `React` name resolves here at render time.
(globalThis as unknown as Record<string, unknown>).React ??= React;
import { describe, expect, it } from "vitest";
import { settledFrame } from "@digithings/hero-banner";
import { DIGIQUANT } from "@digithings/hero-banner/definitions";
import { QuantWordmark } from "@/app/_chrome/QuantWordmark";

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

describe("hero banner server render", () => {
  it("renders the settled DIGIQUANT mark, not a blank canvas", () => {
    const html = renderToStaticMarkup(createElement(QuantWordmark));
    expect(html).toContain('aria-label="digiquant"');
    expect(html).toContain("<canvas");
    // The shape travels as a mask, the colour as a CSS value the host
    // document resolves, so the fallback follows the page theme.
    expect(html).toContain("mask-image:url(");
    expect(html).toContain("background-color:var(--ink)");

    const svg = maskPayload(html);
    expect(svg).toContain("<svg");
    expect(svg).toContain('viewBox="0 0 79 10"');
    expect(svg).toContain('<path d="M');
    expect(svg).toContain('fill-opacity="1"');

    // The fallback must carry the whole mark: one lit pixel per lit cell.
    const frame = settledFrame(DIGIQUANT);
    const lit = frame.pixels.filter((p) => p && p.alpha > 0).length;
    expect(lit).toBeGreaterThan(0);
    expect(maskLitCells(svg)).toBe(lit);
  });

  it("keeps the settled mark while the banner is not armed", () => {
    // The footer arms the banner on the client. Until then (server render,
    // no-JS) the settled mark has to stand in for the canvas.
    const html = renderToStaticMarkup(createElement(QuantWordmark, { armed: false }));
    expect(html).toContain("mask-image:url(");
    expect(maskLitCells(maskPayload(html))).toBeGreaterThan(0);
  });
});
