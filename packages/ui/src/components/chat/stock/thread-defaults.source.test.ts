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

  it("keeps the zero-radius shell", () => {
    expect(thread).toContain('["--composer-radius" as string]: "0"');
    expect(thread).not.toContain("rounded-full");
    expect(thread).not.toContain("rounded-xl");
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
