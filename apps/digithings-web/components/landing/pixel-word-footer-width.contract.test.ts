import { readFileSync } from "node:fs";
import { dirname, join } from "node:path";
import { fileURLToPath } from "node:url";
import { describe, expect, it } from "vitest";

/**
 * The footer wordmark must actually be larger than the band that holds it.
 *
 * `.pixel-word.pixel-word-footer` sizes the mark with `width: min(118%, 1600px)`
 * so it deliberately bleeds past the gutters — that is the whole point of the
 * rule. Two separate things can silently fold it back to 100% and turn the
 * enlargement into a no-op without any visual error:
 *
 * 1. the flex default, which shrinks an over-wide flex item back to the
 *    container's content box, and
 * 2. the blanket `img, svg { max-width: 100% }` reset in
 *    `packages/design/site/site.css`, which the app imports at `globals.css:6`
 *    inside `layer(components)`.
 *
 * `width` and `max-width` are independent properties, so the layer did nothing
 * to save the mark: layered or not, that `max-width: 100%` capped the used
 * width at the band's content box. `flex-shrink: 0` only covers (1); it cannot
 * lift a max-width. Both have to be neutralised, which is what this asserts:
 * the site sheet still caps every svg, so a footer rule whose width exceeds 100%
 * is only honest if it lifts that cap too — and does so *unlayered*, since that
 * is the only way a declaration in this sheet can outrank a layered one.
 */

const here = dirname(fileURLToPath(import.meta.url));

const APP_SHEET = join(here, "..", "..", "app", "globals.css");
const SITE_SHEET = join(here, "..", "..", "..", "..", "packages", "design", "site", "site.css");

/** Comments stripped, so a selector or property named in prose cannot satisfy an assertion. */
function stripComments(css: string): string {
  return css.replace(/\/\*[\s\S]*?\*\//g, "");
}

/** The body of the last rule whose selector list contains `selector`. */
function ruleBody(css: string, selector: string): string {
  const matches = [...stripComments(css).matchAll(/([^{}]+)\{([^{}]*)\}/g)].filter((rule) =>
    rule[1].split(",").some((part) => part.trim() === selector),
  );
  const last = matches.at(-1);
  if (!last) throw new Error(`no rule for selector ${selector}`);
  return last[2];
}

/** Character offsets of any `@layer` block body in `css`, as [start, end). */
function layerRanges(css: string): Array<[number, number]> {
  const ranges: Array<[number, number]> = [];
  const re = /@layer[^{]*\{/g;
  for (const match of css.matchAll(re)) {
    const start = match.index! + match[0].length;
    let depth = 1;
    let cursor = start;
    while (depth > 0) {
      const open = css.indexOf("{", cursor);
      const close = css.indexOf("}", cursor);
      if (close === -1) break;
      if (open !== -1 && open < close) {
        depth += 1;
        cursor = open + 1;
      } else {
        depth -= 1;
        cursor = close + 1;
      }
    }
    ranges.push([start, cursor]);
  }
  return ranges;
}

const appCss = stripComments(readFileSync(APP_SHEET, "utf8"));
const footerRule = ruleBody(appCss, ".pixel-word.pixel-word-footer");
const siteRule = ruleBody(readFileSync(SITE_SHEET, "utf8"), "svg");

describe("footer wordmark width contract", () => {
  it("confirms the site sheet still caps every svg, which is what the rule has to undo", () => {
    expect(siteRule).toMatch(/max-width:\s*100%/);
  });

  it("declares the footer rule unlayered, or the layered clamp outranks it again", () => {
    // The other assertions read the rule's text and stay green no matter what
    // layer it lands in. Cascade layers only arbitrate *between* layers, so
    // wrapping these globals in an `@layer` — or a Tailwind v4 `@import`
    // restructure that moves them into one — would put the footer rule below
    // the site's `layer(components)` clamp and silently re-inert the
    // enlargement. Nothing else in this file would notice.
    const ruleStart = appCss.indexOf(".pixel-word.pixel-word-footer");
    expect(ruleStart).toBeGreaterThan(-1);
    const enclosing = layerRanges(appCss).filter(([start, end]) => ruleStart >= start && ruleStart < end);
    expect(enclosing).toEqual([]);
  });

  it("sizes the footer mark past its container", () => {
    // Guards the premise: if this stops being true the two clamps below are moot.
    expect(footerRule).toMatch(/width:\s*min\(\s*118%/);
  });

  it("lifts the max-width clamp so the enlargement is not a no-op", () => {
    expect(footerRule).toMatch(/max-width:\s*none/);
  });

  it("does not let the flex default shrink the mark back to the band width", () => {
    expect(footerRule).toMatch(/flex-shrink:\s*0/);
  });
});