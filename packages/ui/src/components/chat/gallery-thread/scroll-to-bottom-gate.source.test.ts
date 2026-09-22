import { readFileSync } from "node:fs";
import { dirname, join } from "node:path";
import { fileURLToPath } from "node:url";
import { describe, expect, it } from "vitest";

const here = dirname(fileURLToPath(import.meta.url));

function read(rel: string): string {
  return readFileSync(join(here, rel), "utf8");
}

describe("gallery-thread scroll-to-bottom gate", () => {
  it("reveals the button only when messages are hidden under the composer", () => {
    const source = read("thread.aui.tsx");
    // The gate measures the message list against the composer shell, not a
    // fixed pixel distance from the scroll bottom.
    expect(source).toContain('[data-slot="aui_message-group"]');
    expect(source).toContain('[data-slot="aui_composer-shell"]');
    expect(source).toMatch(
      /group\.getBoundingClientRect\(\)\.bottom >\s*composer\.getBoundingClientRect\(\)\.top/,
    );
    expect(source).not.toContain("distance > 24");
  });

  it("keeps the top-anchored user message off the top edge", () => {
    const css = read(join("..", "..", "..", "styles", "chat-aui.css"));
    expect(css).toMatch(
      /\.digichat-thread__viewport\s+\[data-aui-top-anchor-user\]\s*\{[^}]*padding-top:\s*1\.5rem/,
    );
  });
});
