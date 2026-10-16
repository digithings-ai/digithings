"use client";

import DOMPurify, { type Config } from "dompurify";

/**
 * One sanitizer for every mermaid render path in this package.
 *
 * `mermaid-diagram.tsx` renders through `beautiful-mermaid`, a third-party
 * renderer, and injects the returned string with `dangerouslySetInnerHTML`
 * (inline diagram + zoom overlay). The diagram source is model-authored and
 * therefore attacker-influenceable, so the renderer's output must not reach
 * the DOM unfiltered — a future escapeXml regression upstream should not be
 * able to become XSS here.
 *
 * The other mermaid surface, `ChatMermaidBlock`, renders through mermaid under
 * `securityLevel: "strict"`, whose bundled DOMPurify copy strips scripts,
 * event handlers and `javascript:` URLs before returning. This applies the
 * equivalent policy to the `beautiful-mermaid` path so the two agree: DOMPurify
 * restricted to the SVG namespace, plus `dominant-baseline` (which mermaid's
 * strict config also lets through). The one deliberate divergence is
 * `<foreignObject>`, which mermaid strict admits and this forbids — the
 * HTML-integration escape hatch is not needed by `beautiful-mermaid`, which
 * emits none, and this path runs without HTML labels by design.
 *
 * Fails closed: when there is no DOM (SSR / plain Node) DOMPurify reports
 * `isSupported === false` and cannot sanitize, so this returns "" rather than
 * passing the raw string through. The client render, where a DOM exists, fills
 * the diagram in.
 */
const SANITIZE_CONFIG: Config = {
  USE_PROFILES: { svg: true, svgFilters: true },
  ADD_ATTR: ["dominant-baseline"],
};

export function sanitizeMermaidSvg(svg: string): string {
  if (!DOMPurify.isSupported) return "";
  return DOMPurify.sanitize(svg, SANITIZE_CONFIG);
}
