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

describe("gallery-thread composer renders the Safari block-caret overlay", () => {
  it("mounts ComposerBlockCaret next to the composer input", () => {
    const source = read("thread.aui.tsx");
    expect(source).toMatch(/ComposerBlockCaret/);
    expect(source).toMatch(/from ["']\.\/block-caret["']/);
  });

  it("gates the painted block on engines without caret-shape support", () => {
    const css = readReferenceCss();
    expect(css).toMatch(/@supports not \(caret-shape: block\)/);
    expect(css).toMatch(/\.aui-block-caret/);
    expect(css).toMatch(/caret-color:\s*transparent/);
  });

  it("hides the overlay where the native block caret works", () => {
    const css = readReferenceCss();
    expect(css).toMatch(/@supports \(caret-shape: block\)/);
  });

  it("keeps the block static under reduced motion", () => {
    const css = readReferenceCss();
    expect(css).toMatch(/prefers-reduced-motion/);
  });
});
