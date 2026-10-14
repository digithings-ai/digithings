import { readFileSync } from "node:fs";
import { dirname, join } from "node:path";
import { fileURLToPath } from "node:url";
import { describe, expect, it } from "vitest";

/**
 * The footer wordmark stays inside the page frame (Chris, 11 Oct 2026: "contain
 * it within the vertical grid lines exactly like the digiquant page's banner").
 * It used to be `min(118%, 1600px)` with `max-width: none` and ran off-page.
 * The band now uses digiquant.io's box (frame width plus gutters, centred) and
 * the mark fills that box and no more.
 */

const here = dirname(fileURLToPath(import.meta.url));
const APP_SHEET = join(here, "..", "..", "app", "globals.css");

function stripComments(css: string): string {
  return css.replace(/\/\*[\s\S]*?\*\//g, "");
}

function ruleBody(css: string, selector: string): string {
  const matches = [...stripComments(css).matchAll(/([^{}]+)\{([^{}]*)\}/g)].filter((rule) =>
    rule[1].split(",").some((part) => part.trim() === selector),
  );
  const last = matches.at(-1);
  if (!last) throw new Error(`no rule for selector ${selector}`);
  return last[2];
}

const css = readFileSync(APP_SHEET, "utf8");

describe("footer pixel wordmark is contained in the frame", () => {
  it("never sizes the mark wider than its band", () => {
    const body = ruleBody(css, ".pixel-word.pixel-word-footer");
    expect(body).toMatch(/(^|;|\s)width:\s*100%/);
    expect(body).toMatch(/max-width:\s*100%/);
    expect(body).not.toMatch(/max-width:\s*none/);
    expect(body).not.toMatch(/\b(1[1-9][0-9]|10[1-9])%/);
  });

  it("caps the band at the frame plus gutters, like digiquant.io", () => {
    const body = ruleBody(css, ".pixel-word-band");
    expect(body).toMatch(/max-width:\s*calc\(var\(--frame-w\)\s*\+\s*2\s*\*\s*var\(--page-pad\)\)/);
    expect(body).toMatch(/margin-left:\s*auto/);
    expect(body).toMatch(/margin-right:\s*auto/);
  });
});
