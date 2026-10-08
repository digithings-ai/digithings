import { readFileSync } from "node:fs";
import { dirname, join } from "node:path";
import { fileURLToPath } from "node:url";
import { describe, expect, it } from "vitest";

/**
 * The footer wordmark band (DIG-2304).
 *
 * `.pixel-word-band` wraps `PixelWordmark variant="footer"`: an SVG of
 * `viewBox="0 0 88 10"`, so 88x10 cells at aspect 8.8. Its height is derived
 * from its width, and at wide viewports that is ~150px.
 *
 * PR #5264 gave the band `display: flex` + a fixed `clamp(4.5rem, 12vw, 9rem)`
 * height + `align-items: center` and switched `overflow-x: clip` to
 * `overflow: clip`. A fixed height below the mark's natural height plus
 * `overflow: clip` shaved the top and bottom glyph rows at every viewport wider
 * than ~1280: 7.8px lost at 1440 (~0.5 pixel row), 26px at 1600, 37.8px at
 * 1728. The mark read as squashed.
 *
 * These assertions pin the two CSS properties that make that crop possible, so a
 * future layout change cannot reintroduce it silently. They are static guards,
 * not a substitute for a rendered measurement.
 */
const here = dirname(fileURLToPath(import.meta.url));
const globalsPath = join(here, "globals.css");

/** The body of the first rule with exactly `selector`, or "" when absent. */
function rule(css: string, selector: string): string {
  // Comments are stripped first: this rule carries a rationale comment, and the
  // selector text inside it would otherwise break the boundary match below and
  // silently return "" -- a vacuously passing assertion.
  const bare = css.replace(/\/\*[\s\S]*?\*\//g, "");
  const escaped = selector.replace(/[.*+?^${}()|[\]\\]/g, "\\$&");
  const found = new RegExp(`(?:^|[};])\\s*${escaped}\\s*\\{([^}]*)\\}`, "m").exec(bare);
  return found ? found[1] : "";
}

function declaration(css: string, selector: string, property: string): string | undefined {
  const body = rule(css, selector);
  const found = new RegExp(`(?:^|;)\\s*${property}\\s*:\\s*([^;]+)`).exec(body);
  return found ? found[1].trim() : undefined;
}

describe("footer wordmark band", () => {
  const css = readFileSync(globalsPath, "utf8");

  it("finds both rules, so the assertions below cannot pass vacuously", () => {
    expect(rule(css, ".pixel-word-band")).not.toBe("");
    expect(rule(css, ".pixel-word.pixel-word-footer")).not.toBe("");
  });

  it("never gives the band a fixed height, so the mark cannot be cropped vertically", () => {
    // No height at all (or `auto`) lets the mark set the band height from its own
    // 8.8 aspect ratio. Anything carrying a length -- a clamp, a rem, a px -- is
    // what clipped the glyph rows in #5264.
    const height = declaration(css, ".pixel-word-band", "height");

    if (height !== undefined) {
      expect(height).toBe("auto");
    }
    expect(height ?? "auto").not.toMatch(/clamp\(|[0-9]/);
  });

  it("clips on the horizontal axis only", () => {
    const band = rule(css, ".pixel-word-band");

    // `overflow-x: clip` with the default `overflow-y: visible` is the pair that
    // crops nothing vertically. The bare `overflow: clip` shorthand clips both
    // axes, which is the crop in #5264.
    expect(declaration(css, ".pixel-word-band", "overflow-x")).toBe("clip");
    expect(declaration(css, ".pixel-word-band", "overflow-y")).not.toBe("clip");
    expect(band).not.toMatch(/(?:^|;)\s*overflow\s*:\s*clip/);
  });

  it("keeps the footer mark inside the padded band rather than bleeding past it", () => {
    // The mark is 88 cells wide and the band clips horizontally, so any width
    // over 100% eats the outer columns of the first and last letter: at 1440 the
    // #5264 value of 118% lost 3.8 cells a side. Whether the footer should bleed
    // at all is the Designer's call (DIG-2304); until that ruling the mark fits.
    const width = declaration(css, ".pixel-word.pixel-word-footer", "width");

    expect(width).toBe("min(100%, 1400px)");
    expect(width).not.toMatch(/(?:1[0-9]|[2-9][0-9])%/);
  });
});
