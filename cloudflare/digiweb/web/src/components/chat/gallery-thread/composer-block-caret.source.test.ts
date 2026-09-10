import { readFileSync } from "node:fs";
import { dirname, join } from "node:path";
import { fileURLToPath } from "node:url";
import { describe, expect, it } from "vitest";

const here = dirname(fileURLToPath(import.meta.url));

function read(rel: string): string {
  return readFileSync(join(here, rel), "utf8");
}

function readReferenceCss(): string {
  return readFileSync(
    join(here, "..", "..", "..", "..", "..", "reference", "app", "(chatbot)", "chatbot", "chatbot.css"),
    "utf8",
  );
}

/** Slice css from the first occurrence of `from` (inclusive) to the first `to` after it. */
function sliceBetween(css: string, from: string, to: string): string {
  const start = css.indexOf(from);
  const end = css.indexOf(to, start + from.length);
  expect(start).toBeGreaterThanOrEqual(0);
  expect(end).toBeGreaterThan(start);
  return css.slice(start, end);
}

describe("gallery-thread composer renders the Safari block-caret overlay", () => {
  it("mounts ComposerBlockCaret next to the composer input", () => {
    const source = read("thread.aui.tsx");
    expect(source).toContain('import { ComposerBlockCaret } from "./block-caret";');
    expect(source).toMatch(/<ComposerBlockCaret containerRef=\{/);
  });

  it("documents the Safari fallback before the feature guard", () => {
    const css = readReferenceCss();
    const comment = css.indexOf("Painted block caret");
    const guard = css.indexOf("@supports not (caret-shape: block)");
    expect(comment).toBeGreaterThanOrEqual(0);
    expect(guard).toBeGreaterThan(comment);
  });

  it("hides the overlay where the native block caret works", () => {
    const css = readReferenceCss();
    const hideBlock = sliceBetween(css, "@supports (caret-shape: block)", "@supports not (caret-shape: block)");
    expect(hideBlock).toContain(".aui-block-caret");
    expect(hideBlock).toMatch(/display:\s*none/);
  });

  it("paints the block and hides the native caret only without caret-shape support", () => {
    const css = readReferenceCss();
    const paintBlock = sliceBetween(css, "@supports not (caret-shape: block)", "@keyframes aui-caret-blink");
    expect(paintBlock).toMatch(/\.aui-composer-input\s*\{[^}]*caret-color:\s*transparent/);
    expect(paintBlock).toMatch(/\.aui-block-caret\s*\{[^}]*display:\s*block/);
  });

  it("keeps the block static under reduced motion", () => {
    const css = readReferenceCss();
    const motionBlock = sliceBetween(css, "@media (prefers-reduced-motion: reduce)", "@keyframes aui-caret-blink");
    expect(motionBlock).toContain(".aui-block-caret");
    expect(motionBlock).toMatch(/animation:\s*none/);
  });
});
