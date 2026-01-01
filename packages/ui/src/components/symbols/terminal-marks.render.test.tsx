/**
 * SSR smoke tests for the terminal identity: the mark carries its `variant`
 * geometry and stays decorative unless titled, the wordmark renders as plain
 * mono text at weight 400, and the hairline cut ships the stroke ratio that
 * makes its overlapping contours read.
 */
import { renderToStaticMarkup } from "react-dom/server";
import { describe, expect, it } from "vitest";

import { HairlineWordmark, TerminalMark, TerminalWordmark } from "./terminal-marks";

describe("TerminalMark", () => {
  it("renders the full lockup, decorative by default", () => {
    const html = renderToStaticMarkup(<TerminalMark />);
    expect(html).toContain("terminal-mark");
    expect(html).toContain('aria-hidden="true"');
    expect(html).toContain('width="22"');
    expect(html).toContain('fill="currentColor"');
    // the block cursor is a rect, not a glyph
    expect(html).toContain("<rect");
  });

  it("draws fewer glyphs in the compact reduction than the full lockup", () => {
    const count = (html: string) => html.split("<path").length - 1;
    const full = renderToStaticMarkup(<TerminalMark />);
    const compact = renderToStaticMarkup(<TerminalMark variant="compact" />);
    // full is `digi` (4 glyphs), compact is `d` (1) — both plus one cursor rect
    expect(count(full)).toBeGreaterThan(count(compact));
    expect(count(compact)).toBe(1);
    expect(compact).toContain("<rect");
  });

  it("exposes a titled mark as an image", () => {
    const html = renderToStaticMarkup(<TerminalMark title="digithings" />);
    expect(html).toContain('role="img"');
    expect(html).toContain("<title>digithings</title>");
    expect(html).not.toContain("aria-hidden");
  });

  it("passes size through and merges a caller class", () => {
    const html = renderToStaticMarkup(<TerminalMark size={44} className="nav-brand" />);
    expect(html).toContain('width="44"');
    expect(html).toContain("terminal-mark nav-brand");
  });

  it("keeps the mark's ink inside the viewBox so a circular crop cannot clip it", () => {
    // the cursor is the extreme element; `vertical-align: -0.16em` is easy to
    // invert, which draws it 0.32em high and lets an avatar crop shave a corner
    const html = renderToStaticMarkup(<TerminalMark />);
    const rect = /<rect x="([\d.]+)" y="([\d.]+)" width="([\d.]+)" height="([\d.]+)"/.exec(html);
    expect(rect).not.toBeNull();
    const [x, y, w, h] = rect!.slice(1).map(Number);
    expect(x).toBeGreaterThanOrEqual(0);
    expect(y).toBeGreaterThanOrEqual(0);
    expect(x + w).toBeLessThanOrEqual(100);
    expect(y + h).toBeLessThanOrEqual(100);
  });
});

describe("TerminalWordmark", () => {
  it("renders plain mono text at weight 400, tracking 0", () => {
    const html = renderToStaticMarkup(<TerminalWordmark suffix="things" />);
    expect(html).toContain("terminal-wordmark");
    expect(html).toContain("font-mono");
    expect(html).toContain("font-normal");
    expect(html).toContain("tracking-normal");
    expect(html).toContain("digi");
    expect(html).toContain("things");
  });

  it("does not dress the suffix in the accent — the terminal cut is one tone", () => {
    const html = renderToStaticMarkup(<TerminalWordmark suffix="quant" />);
    expect(html).not.toContain("text-accent");
  });

  it("accepts a custom prefix", () => {
    const html = renderToStaticMarkup(<TerminalWordmark prefix="olym" suffix="pus" />);
    expect(html).toContain("olym");
    expect(html).toContain("pus");
  });
});

describe("HairlineWordmark", () => {
  it("strokes rather than fills, at the site's 0.538%-of-em ratio", () => {
    const html = renderToStaticMarkup(<HairlineWordmark word="things" />);
    expect(html).toContain("hairline-wordmark");
    expect(html).toContain('fill="none"');
    expect(html).toContain('stroke="currentColor"');
    expect(html).toContain('stroke-opacity="0.3"');
    // 1/186 of the em — a 1px line on a ~186px glyph. Compared numerically:
    // asserting the serialised float pins a decimal expansion, not the ratio.
    const sw = /stroke-width="([\d.]+)"/.exec(html);
    expect(sw).not.toBeNull();
    expect(Number(sw![1])).toBeCloseTo(1000 / 186, 6);
  });

  it("draws one path per glyph for each word", () => {
    const count = (html: string) => html.split("<path").length - 1;
    expect(count(renderToStaticMarkup(<HairlineWordmark word="things" />))).toBe(10);
    expect(count(renderToStaticMarkup(<HairlineWordmark word="quant" />))).toBe(9);
  });

  it("exposes a titled wordmark as an image", () => {
    const html = renderToStaticMarkup(<HairlineWordmark word="quant" title="digiquant" />);
    expect(html).toContain('role="img"');
    expect(html).toContain("<title>digiquant</title>");
    expect(html).not.toContain("aria-hidden");
  });
});
