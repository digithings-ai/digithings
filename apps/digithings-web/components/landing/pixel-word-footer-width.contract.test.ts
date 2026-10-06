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
 *    `packages/design/site/site.css`, which the app imports at
 *    `globals.css:6`. That rule sits in `layer(components)`, so it loses to any
 *    unlayered `width` — which is why the mark *looked* correctly sized — but
 *    nothing unlayered declared a `max-width`, so the clamp still applied and
 *    capped the used width at the band's content box.
 *
 * `flex-shrink: 0` only covers (1); it does nothing about a max-width cap. Both
 * have to be neutralised, which is what this asserts: the site sheet still caps
 * every svg, so a footer rule whose width exceeds 100% is only honest if it
 * lifts that cap too.
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

const footerRule = ruleBody(readFileSync(APP_SHEET, "utf8"), ".pixel-word.pixel-word-footer");
const siteRule = ruleBody(readFileSync(SITE_SHEET, "utf8"), "svg");

describe("footer wordmark width contract", () => {
  it("confirms the site sheet still caps every svg, which is what the rule has to undo", () => {
    expect(siteRule).toMatch(/max-width:\s*100%/);
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