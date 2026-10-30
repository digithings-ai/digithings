import { readFileSync } from "node:fs";
import { dirname, join } from "node:path";
import { fileURLToPath } from "node:url";
import { describe, expect, it } from "vitest";

const here = dirname(fileURLToPath(import.meta.url));
const thread = readFileSync(join(here, "thread.aui.tsx"), "utf8");

describe("stock Thread defaults", () => {
  it("ships house copy, not the generic chat placeholder", () => {
    expect(thread).not.toContain("How can I help you today?");
    expect(thread).toContain("Ask the stack.");
    expect(thread).toContain("It reads the configured docs, then answers.");
  });

  // assistant-ui's default rounded shapes (base registry, r.assistant-ui.com/base,
  // @assistant-ui/react ^0.15.32): 1rem composer and user bubble, round
  // composer buttons and scroll-to-bottom, rounded-xl menu and skeletons.
  it("follows assistant-ui's default radii, not a zero-radius shell", () => {
    expect(thread).toContain('["--composer-radius" as string]: "1rem"');
    expect(thread).not.toContain('["--composer-radius" as string]: "0"');
    expect(thread).not.toContain("rounded-none");
    expect(thread).toMatch(/aui-user-message-content[^"]*rounded-\(--composer-radius\)/);
    expect(thread).toMatch(/aui-composer-send size-7 rounded-full/);
    expect(thread).toMatch(/aui-composer-cancel size-7 rounded-full/);
    expect(thread).toMatch(/aui-thread-scroll-to-bottom[^"]*rounded-full/);
    expect(thread).toMatch(/aui-thread-welcome-suggestion [^"]*rounded-md/);
    expect(thread).toMatch(/w-2\/5 rounded-xl/);
    expect(thread).toContain("<StockShapeProvider>");
  });

  it("keeps the composer placeholder at AA contrast", () => {
    expect(thread).toContain("placeholder:text-ink-mute");
    expect(thread).not.toContain("placeholder:text-ink-mute/60");
  });

  it("uses the cube matrix for the working indicator, not a pulsing glyph", () => {
    expect(thread).toContain('<DotMatrix state="loading" decorative');
    expect(thread).toContain('role="status"');
    expect(thread).not.toContain('{"●"}');
  });
});
