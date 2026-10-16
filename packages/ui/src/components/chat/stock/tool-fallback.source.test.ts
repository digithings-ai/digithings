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

  it("names the status icon through the shared DotMatrix (DIG-3449)", () => {
    expect(source).toMatch(/from ["']\.\.\/DotMatrix["']/);
    expect(source).toMatch(/<DotMatrix/);
    expect(source).toMatch(/label=\{label\}/);
    expect(source).not.toMatch(/LoaderIcon/);
    expect(source).not.toMatch(/CheckIcon/);
    expect(source).not.toMatch(/XCircleIcon/);
    expect(source).not.toMatch(/AlertCircleIcon/);
  });

  it("gives the trigger label the foreground token for contrast (DIG-3449)", () => {
    expect(source).toMatch(
      /tool-fallback-trigger-label-wrapper[^"]*text-foreground/,
    );
  });
});
