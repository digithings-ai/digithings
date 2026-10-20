import { readFileSync } from "node:fs";
import { dirname, join } from "node:path";
import { fileURLToPath } from "node:url";
import { describe, expect, it } from "vitest";

const here = dirname(fileURLToPath(import.meta.url));

function read(rel: string): string {
  return readFileSync(join(here, rel), "utf8");
}

function readPackageCss(): string {
  // WS1: the digichat grammar sheet moved from the reference gallery into the
  // package (packages/ui/src/styles/chat-digichat.css).
  return readFileSync(join(here, "..", "..", "..", "styles", "chat-digichat.css"), "utf8");
}

/** Slice css from the first occurrence of `from` (inclusive) to the first `to` after it. */
function sliceBetween(css: string, from: string, to: string): string {
  const start = css.indexOf(from);
  const end = css.indexOf(to, start + from.length);
  expect(start).toBeGreaterThanOrEqual(0);
  expect(end).toBeGreaterThan(start);
  return css.slice(start, end);
}

describe("gallery-thread composer renders the painted block caret", () => {
  it("mounts ComposerBlockCaret next to the composer input", () => {
    const source = read("thread.aui.tsx");
    expect(source).toContain('import { ComposerBlockCaret } from "./block-caret";');
    expect(source).toMatch(/<ComposerBlockCaret containerRef=\{/);
  });

  it("paints the block on every engine, not only where caret-shape is missing", () => {
    const css = readPackageCss();
    expect(css).not.toContain("@supports not (caret-shape: block)");
    expect(css).not.toContain("@supports (caret-shape: block)");
    expect(css).toContain("Painted block caret");
  });

  it("hides the native caret and shows the block only while focused", () => {
    const css = readPackageCss();
    const paintBlock = sliceBetween(css, "/* Painted block caret", "@keyframes aui-caret-blink");
    expect(paintBlock).toMatch(/caret-color:\s*transparent\s*!important/);
    expect(paintBlock).toMatch(/\.aui-block-caret\s*\{[^}]*display:\s*none/);
    expect(paintBlock).toMatch(/\.aui-composer-input:focus[\s\S]*?display:\s*block/);
  });

  it("draws a block as tall as a native cursor, standing on the baseline", () => {
    const caret = read("block-caret.tsx");
    // Height comes from the font's own ascent + descent, and the block's
    // bottom edge lands on the baseline so it never hangs below the letters.
    expect(caret).toContain("fontVerticalMetrics");
    expect(caret).toContain("ascent + descent");
    expect(caret).toContain("baseline - caretHeight");
    // The measured path hangs the block from the text's own baseline.
    expect(caret).toContain("mirrored.baseline");
  });

  it("keeps the block static under reduced motion", () => {
    const css = readPackageCss();
    const motionBlock = sliceBetween(css, "@media (prefers-reduced-motion: reduce)", "@keyframes aui-caret-blink");
    expect(motionBlock).toContain(".aui-block-caret");
    expect(motionBlock).toMatch(/animation:\s*none/);
  });
});
