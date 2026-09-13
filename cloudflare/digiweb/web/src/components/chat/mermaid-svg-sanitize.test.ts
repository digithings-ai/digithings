// @vitest-environment jsdom
/**
 * `sanitizeMermaidSvg` — the guard between a third-party mermaid renderer and
 * `dangerouslySetInnerHTML`.
 *
 * Runs under jsdom, not the suite's usual happy-dom, on purpose: DOMPurify
 * needs a spec-compliant DOM to make its allow/deny decisions, and happy-dom's
 * SVG parsing is not it. Measured on this exact dependency set, happy-dom made
 * `DOMPurify.sanitize` return "" for a pristine diagram (over-stripping) and
 * pass `<script>`/`onerror` through untouched when handed a node
 * (under-stripping) — either way the assertions below would test happy-dom's
 * parser, not our policy. jsdom is DOMPurify's reference environment.
 */
import { describe, expect, it } from "vitest";

import { sanitizeMermaidSvg } from "./sanitize-mermaid-svg";

const wrap = (body: string) =>
  `<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 10 10">${body}</svg>`;

describe("sanitizeMermaidSvg", () => {
  it("drops a <script> element while keeping the diagram", () => {
    const out = sanitizeMermaidSvg(
      wrap('<script>alert(1)</script><rect width="5" height="5"/>'),
    );
    expect(out.toLowerCase()).not.toContain("<script");
    expect(out).not.toContain("alert(1)");
    expect(out).toContain("<rect");
  });

  it("drops every on* event-handler attribute", () => {
    const out = sanitizeMermaidSvg(
      wrap(
        '<rect width="5" height="5" onload="alert(1)" onerror="alert(2)" onclick="alert(3)"/>',
      ),
    );
    expect(out).not.toMatch(/on\w+=/i);
    expect(out).toContain("<rect");
    expect(out).toContain('width="5"');
  });

  it("drops javascript: URLs on links", () => {
    const out = sanitizeMermaidSvg(
      wrap(
        '<a href="javascript:alert(1)" xlink:href="javascript:alert(2)"><text>x</text></a>',
      ),
    );
    expect(out).not.toContain("javascript:");
    expect(out).toContain("<text>x</text>");
  });

  it("drops <foreignObject>, the HTML-integration escape hatch", () => {
    const out = sanitizeMermaidSvg(
      wrap(
        '<foreignObject><body xmlns="http://www.w3.org/1999/xhtml"><img src="x" onerror="alert(1)"/></body></foreignObject><rect/>',
      ),
    );
    expect(out).not.toMatch(/foreignObject/i);
    expect(out).not.toMatch(/on\w+=/i);
    expect(out).toContain("<rect");
  });

  it("keeps a real diagram's elements, presentation attrs and CSS", () => {
    const diagram = wrap(
      [
        "<style>text{font-family:Inter;fill:var(--fg)}</style>",
        '<defs><marker id="arrowhead" markerWidth="8" refX="7" orient="auto"><polygon points="0 0, 8 2.5, 0 5" fill="var(--accent)"/></marker></defs>',
        '<g class="node" data-id="A" data-shape="rect">',
        '<rect width="40" height="20" rx="4" fill="var(--node-fill)" stroke="var(--border)"/>',
        '<text x="20" y="14" dominant-baseline="middle" text-anchor="middle">digichat</text>',
        '<polyline points="0,0 10,10" marker-end="url(#arrowhead)"/>',
        "</g>",
      ].join(""),
    );
    const out = sanitizeMermaidSvg(diagram);
    expect(out).toContain("<style>");
    expect(out).toContain("<defs>");
    expect(out).toContain("<marker");
    expect(out).toContain('dominant-baseline="middle"');
    expect(out).toContain('marker-end="url(#arrowhead)"');
    expect(out).toContain('fill="var(--node-fill)"');
    expect(out).toContain('data-id="A"');
    expect(out).toMatch(/<text[^>]*>digichat<\/text>/);
  });
});
