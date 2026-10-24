import { readFileSync } from "node:fs";
import { describe, expect, test } from "bun:test";

import { createElement } from "react";
import { renderToStaticMarkup } from "react-dom/server";

import { DIGICHAT, DIGIQUANT } from "../src/definitions";
import { HeroBanner } from "../src/web";

const SRC = readFileSync(new URL("../src/web.tsx", import.meta.url), "utf8");

/** What the server - and a page with JavaScript off - actually ships. */
describe("server render and no-JS fallback", () => {
  test("paints the settled mark as a CSS mask, not an empty canvas", () => {
    const html = renderToStaticMarkup(createElement(HeroBanner, { def: DIGIQUANT }));
    expect(html).toContain('role="img"');
    expect(html).toContain('aria-label="digiquant"');
    expect(html).toContain("background-color:var(--ink)");
    expect(html).toContain("mask-image:");
    expect(html).toContain("data:image/svg+xml");
    expect(html).toMatch(/^<canvas [^>]*><\/canvas>$/);
  });

  test("a fixed-tone definition carries its own colour", () => {
    const html = renderToStaticMarkup(createElement(HeroBanner, { def: DIGICHAT }));
    expect(html).toContain("background-color:#D7D7D7");
  });

  test("an unarmed banner ships the fallback and starts no script", () => {
    const html = renderToStaticMarkup(createElement(HeroBanner, { def: DIGIQUANT, armed: false }));
    expect(html).toContain("mask-image:");
    expect(html).not.toContain("undefined");
  });
});

/**
 * The effect itself needs a DOM and a canvas, which this package's `bun test`
 * runner does not provide. These assert the wiring that the gating depends on;
 * the pause semantics are covered by clock.test.ts.
 */
describe("repaint loop wiring", () => {
  test("pauses when the tab is hidden", () => {
    expect(SRC).toContain('document.addEventListener("visibilitychange", onVisibilityChange)');
    expect(SRC).toContain('document.removeEventListener("visibilitychange", onVisibilityChange)');
    expect(SRC).toContain('document.visibilityState !== "hidden"');
  });

  test("pauses when the mark is off screen", () => {
    expect(SRC).toContain("new IntersectionObserver");
    expect(SRC).toContain("intersection?.observe(canvas)");
    expect(SRC).toContain("intersection?.disconnect()");
    expect(SRC).toContain("clock.pause(performance.now())");
  });

  test("follows prefers-reduced-motion without a remount", () => {
    expect(SRC).toContain('matchMedia?.("(prefers-reduced-motion: reduce)")');
    expect(SRC).toContain('reduced?.addEventListener?.("change", onMotionChange)');
    expect(SRC).toContain('reduced?.removeEventListener?.("change", onMotionChange)');
  });

  test("clears the timer and the pending frame on unmount", () => {
    expect(SRC).toContain("clearTimeout(timer)");
    expect(SRC).toContain("cancelAnimationFrame(raf)");
    expect(SRC).toMatch(/return \(\) => \{\s*stop\(\);/);
    expect(SRC).toContain("themeWatch?.disconnect()");
  });
});
