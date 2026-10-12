import { renderToStaticMarkup } from "react-dom/server";
import { describe, expect, it } from "vitest";

import { DigichatWordmark } from "./DigichatWordmark";
import { SHADES, wordmarkPixels } from "./digichat-wordmark";

describe("DigichatWordmark", () => {
  it("paints the settled word as square pixels with no radius", () => {
    const html = renderToStaticMarkup(<DigichatWordmark />);
    const mark = wordmarkPixels();
    const channel = SHADES.rest.rgb.toString(16);
    expect(html).toContain('aria-label="digichat"');
    expect(html).toContain('shape-rendering="crispEdges"');
    expect(html).toContain('rx="0"');
    expect(html).toContain('ry="0"');
    expect(html).toContain("border-radius:0");
    expect(html).not.toContain("38;5");
    expect(html).not.toMatch(/#(?:00|0a|14)?[0-9a-f]*teal/i);
    expect(html.match(/<rect /g)?.length).toBe(mark.pixels.length);
    expect(html).toContain(`fill="#${channel}${channel}${channel}"`);
    expect(html).not.toContain('width="2"');
  });
});
