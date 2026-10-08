import { readFileSync } from "node:fs";
import { join } from "node:path";
import { describe, expect, it } from "vitest";

/**
 * DIG-2304: the footer wordmark must not be cropped by its own band.
 *
 * PR #5264 gave `.pixel-word-band` a fixed height and `overflow: clip`, so the
 * mark lost its top and bottom glyph rows at every viewport past ~1280 — 7.8px
 * at 1440, 26.0px at 1600, 37.8px at 1728 — and read as squashed. A string
 * assertion cannot catch that class of bug: it is arithmetic, so this file
 * reproduces the arithmetic Chrome does and reads the declarations it feeds on
 * out of the real stylesheet.
 *
 * Two things keep it honest. The model is fed the *parsed* declarations of the
 * live rules, so reverting the fix fails these tests rather than passing them.
 * And `teeth` below replays the pre-fix declarations through the same model and
 * requires it to report the crop, so the assertions cannot pass by being
 * vacuous. The table that `teeth` reproduces is the review's measured table.
 *
 * These two rules are also the design seat's ruling (DIG-2353, verdict on
 * DIG-2364): the footer mark stays inside the band, whole. So the band has no
 * height of its own and the vertical space is padding, and the mark is never
 * wider than the band. Both are asserted here so neither can come back
 * unnoticed.
 */

const CSS_PATH = join(__dirname, "globals.css");
const MARK_PATH = join(__dirname, "../components/landing/PixelWordmark.tsx");

const css = readFileSync(CSS_PATH, "utf8");
const markSrc = readFileSync(MARK_PATH, "utf8");

/** --page-pad, from packages/design/tokens.css: --page-pad: var(--gutter). */
const PAGE_PAD = "clamp(1.25rem, 4vw, 3.25rem)";

/** The viewBox the mark actually renders with; the model's aspect comes from it. */
const VIEWBOX = markSrc.match(/viewBox="0 0 (\d+) (\d+)"/);
if (!VIEWBOX) throw new Error(`no viewBox="0 0 W H" in ${MARK_PATH}`);
const ASPECT = Number(VIEWBOX[1]) / Number(VIEWBOX[2]);

const VIEWPORTS = [1280, 1440, 1600, 1728, 1920];

/** Everything a flex or block layout needs here is one of these. */
type Length = { px: number } | { percent: number } | { raw: string };

type Decls = Record<string, Length>;

/**
 * The declarations of every top-level rule for `selector`. Depth 0 only: the
 * `.pixel-word` widths inside the `min-width` media queries must not leak in.
 */
function declarations(source: string, selector: string): Decls {
  // Comments sit between rules and would otherwise end up in the prelude.
  const styles = source.replace(/\/\*[\s\S]*?\*\//g, "");
  const found: Decls = {};
  let depth = 0;
  let start = 0;

  for (let i = 0; i <= styles.length; i++) {
    const char = styles[i];
    if (char === "{") {
      if (depth === 0) {
        const prelude = styles.slice(start, i);
        if (prelude.trim() === selector) {
          const body = styles.slice(i + 1, styles.indexOf("}", i));
          for (const chunk of body.split(";")) {
            const at = chunk.indexOf(":");
            if (at < 0) continue;
            const property = chunk.slice(0, at).trim();
            const value = chunk.slice(at + 1).trim();
            if (property) found[property] = parseLength(value);
          }
        }
      }
      depth += 1;
    } else if (char === "}") {
      depth -= 1;
      if (depth === 0) start = i + 1;
    }
  }

  if (!Object.keys(found).length) throw new Error(`no top-level rule for ${selector}`);
  return found;
}

function parseLength(value: string): Length {
  const raw = value.trim();
  const percent = raw.match(/^([\d.]+)%$/);
  if (percent) return { percent: Number(percent[1]) };
  const px = raw.match(/^(-?[\d.]+)px$/);
  if (px) return { px: Number(px[1]) };
  return { raw };
}

const REM = 16;

/** Resolves px, %-of-basis, and the clamp()/rem forms these rules actually use. */
function resolve(length: Length | undefined, basis: number): number | null {
  if (length === undefined) return null;
  if ("px" in length) return length.px;
  if ("percent" in length) return (length.percent / 100) * basis;
  const raw = length.raw;
  if (raw === "auto") return null;

  const clamp = raw.match(/^clamp\((.+)\)$/);
  if (clamp) {
    const parts = clamp[1].split(",").map((part) => resolveLength(part, basis));
    return Math.min(Math.max(parts[0], parts[1]), parts[2]);
  }
  const single = raw.match(/^(.+)$/);
  return single ? resolveLength(single[1], basis) : null;
}

function resolveLength(token: string, basis: number): number {
  const value = token.trim();
  if (value.endsWith("rem")) return Number(value.slice(0, -3)) * REM;
  if (value.endsWith("vw")) return (Number(value.slice(0, -2)) / 100) * basis;
  if (value.endsWith("%")) return (Number(value.slice(0, -1)) / 100) * basis;
  const px = value.match(/^(-?[\d.]+)px$/);
  if (px) return Number(px[1]);
  throw new Error(`cannot resolve length: ${value}`);
}

/** `min(100%, 1400px)` and `min(118%, 1600px)` both resolve against `basis`. */
function minOf(raw: string, basis: number): number {
  const min = raw.match(/^min\((.+)\)$/);
  if (!min) throw new Error(`not a min(): ${raw}`);
  return Math.min(...min[1].split(",").map((token) => resolveLength(token, basis)));
}

const CLIPS: ReadonlySet<string> = new Set(["hidden", "clip", "scroll", "auto"]);

/**
 * Computed overflow-y, following the one pairing rule that matters here: a
 * `clip`/`visible` pair is kept as written, anything else paired with `visible`
 * coerces it to `auto`, which does clip. The fix depends on that distinction.
 */
function computedOverflowY(decls: Decls): string {
  const shorthand = resolveKeyword(decls, "overflow");
  const y = resolveKeyword(decls, "overflow-y");
  const x = resolveKeyword(decls, "overflow-x");
  if (shorthand) return shorthand;
  if (!y) return x === "clip" ? "visible" : "visible";
  return y;
}

function resolveKeyword(decls: Decls, property: string): string | null {
  const length = decls[property];
  if (!length || !("raw" in length)) return null;
  return length.raw;
}

type Frame = {
  viewport: number;
  /** Content-box width available to the mark. */
  contentWidth: number;
  /** Content-box height available to the mark. */
  contentHeight: number;
  markWidth: number;
  markHeight: number;
  /** Pixels of the mark the band hides. 0 on both axes is the whole point. */
  cropY: number;
  cropX: number;
};

/**
 * Lays the band out at every viewport the review measured. `flex` covers the
 * pre-fix shape: the band was a flex row, so a mark wider than the band was
 * shrunk back to it (flex-shrink defaults to 1) and only then measured.
 */
function measure(styles: string): Frame[] {
  const band = declarations(styles, ".pixel-word-band");
  const mark = declarations(styles, ".pixel-word.pixel-word-footer");

  // A flex band shrinks an over-wide mark back to its content box before the
  // crop is computed (flex-shrink defaults to 1), so the shrink has to be in
  // the model or the numbers miss the browser's.
  const flex = resolveKeyword(band, "display") === "flex";

  const overflowY = computedOverflowY(band);
  const clipsY = CLIPS.has(overflowY);
  const clipsX = CLIPS.has(resolveKeyword(band, "overflow-x") ?? computedOverflowY(band));

  return VIEWPORTS.map((viewport) => {
    // vw and % both resolve against this viewport, so the basis is per-frame.
    const bandHeight = resolve(band.height, viewport);
    const markHeightDecl = resolve(mark.height, viewport);
    const contentWidth = viewport - 2 * (resolve({ raw: PAGE_PAD }, viewport) ?? 0);

    let markWidth = minOf(resolveKeyword(mark, "width") ?? "", contentWidth);
    if (flex && markWidth > contentWidth) markWidth = contentWidth;

    const natural = markWidth / ASPECT;
    const markHeight = markHeightDecl ?? natural;

    // No declared height, or `auto`: the band grows to whatever the mark needs.
    const contentHeight = bandHeight ?? markHeight;

    return {
      viewport,
      contentWidth,
      contentHeight,
      markWidth,
      markHeight,
      cropY: clipsY ? Math.max(0, markHeight - contentHeight) : 0,
      cropX: clipsX ? Math.max(0, markWidth - contentWidth) : 0,
    };
  });
}

/** The pre-fix declarations, verbatim from PR #5264. */
const BROKEN = `
.pixel-word-band {
  display: flex;
  justify-content: center;
  align-items: center;
  height: clamp(4.5rem, 12vw, 9rem);
  padding-left: var(--page-pad);
  padding-right: var(--page-pad);
  overflow: clip;
}

.pixel-word.pixel-word-footer {
  width: min(118%, 1600px);
  height: auto;
  margin: 0;
  margin-top: 0;
}
`;

describe("footer wordmark band (DIG-2304)", () => {
  it("keeps the viewBox the model assumes", () => {
    // 88x10 -> 8.8, the figure the globals.css comment cites.
    expect(`${VIEWBOX[1]}x${VIEWBOX[2]}`).toBe("88x10");
    expect(ASPECT).toBe(8.8);
  });

  it("gives the band no height, so the mark sets it", () => {
    const band = declarations(css, ".pixel-word-band");
    expect(band.height).toBeUndefined();
    expect(band.minHeight).toBeUndefined();
    expect(band.maxHeight).toBeUndefined();
  });

  it("clips the horizontal axis only", () => {
    const band = declarations(css, ".pixel-word-band");
    expect(resolveKeyword(band, "overflow")).toBeNull();
    expect(computedOverflowY(band)).toBe("visible");
  });

  it.each(VIEWPORTS)("crops no glyph rows at %ipx", (viewport) => {
    const frame = measure(css).find((f) => f.viewport === viewport);
    expect(frame).toBeDefined();
    expect(frame!.cropY).toBe(0);
  });

  it.each(VIEWPORTS)("keeps the whole mark inside the band at %ipx", (viewport) => {
    const frame = measure(css).find((f) => f.viewport === viewport);
    expect(frame).toBeDefined();
    expect(frame!.cropX).toBe(0);
    expect(frame!.markWidth).toBeLessThanOrEqual(frame!.contentWidth);
  });

  it("fits the mark to the padded band at 1440, where the bleed started", () => {
    const frame = measure(css).find((f) => f.viewport === 1440)!;
    expect(frame.contentWidth).toBe(1336);
    expect(frame.markWidth).toBe(1336);
    expect(frame.markHeight).toBeCloseTo(frame.contentHeight, 6);
  });

  // The ruling: the band's vertical space is padding, not a height. If padding
  // went away the band would collapse onto the mark instead of holding it, and
  // that is a different page, so it is pinned here too.
  it("takes the band's vertical space from padding, not from a height", () => {
    const band = declarations(css, ".pixel-word-band");
    const padding = resolveKeyword(band, "padding");
    expect(padding).toBe("clamp(3rem, 8vw, 6rem) var(--page-pad) 0");
    // At the review's widths 8vw is between the 3rem floor and the 6rem ceiling.
    for (const viewport of [1440, 1728, 1920]) {
      const top = Math.min(Math.max(3 * REM, (8 / 100) * viewport), 6 * REM);
      expect(top).toBeGreaterThanOrEqual(3 * REM);
      expect(top).toBeLessThanOrEqual(6 * REM);
    }
  });

  // The other half of the ruling: contained, not bleeding. The mark must not
  // exceed the band's content box at any width, in either rule's terms.
  it("keeps the mark inside the band rather than bleeding it", () => {
    const mark = declarations(css, ".pixel-word.pixel-word-footer");
    expect(resolveKeyword(mark, "width")).toBe("min(100%, 1400px)");
    expect(resolveKeyword(mark, "margin")).toBe("0 auto");
    for (const frame of measure(css)) {
      expect(frame.cropX).toBe(0);
      expect(frame.markWidth).toBeLessThanOrEqual(frame.contentWidth);
    }
  });
});

/**
 * The teeth. If these stop reproducing the review's table, the model above is
 * not the browser's arithmetic and its green is worth nothing.
 */
describe("the crop model has teeth", () => {
  const before = measure(BROKEN);

  it.each([
    [1280, 0],
    [1440, 7.8],
    [1600, 26],
    [1728, 37.8],
  ])("reproduces the %ipx crop of PR #5264 (%ipx)", (viewport, expected) => {
    const frame = before.find((f) => f.viewport === viewport)!;
    expect(frame.cropY).toBeCloseTo(expected, 1);
  });

  it("would fail the live assertions if the fix were reverted", () => {
    expect(measure(css).every((f) => f.cropY === 0)).toBe(true);
    expect(before.filter((f) => f.cropY > 0).length).toBeGreaterThan(0);
  });
});