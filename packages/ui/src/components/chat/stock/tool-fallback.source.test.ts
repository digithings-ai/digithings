import { readFileSync } from "node:fs";
import { dirname, join } from "node:path";
import { fileURLToPath } from "node:url";
import { describe, expect, it } from "vitest";

const here = dirname(fileURLToPath(import.meta.url));
const source = readFileSync(join(here, "tool-fallback.aui.tsx"), "utf8");

describe("stock ToolFallback source guard", () => {
  it("reads attribution through the shared @digithings/ui helper", () => {
    expect(source).toMatch(
      /import\s*\{\s*readGloomberbAttribution\s*\}\s*from\s*["']@digithings\/ui["']/,
    );
  });

  it("never hardcodes the canonical strings or the terminal URL", () => {
    expect(source).not.toContain("Sourced from Gloomberb");
    expect(source).not.toContain("Data delayed up to 15 minutes");
    expect(source).not.toContain("https://term.gloom.sh");
  });
});
