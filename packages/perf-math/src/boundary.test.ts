import { readdirSync, readFileSync } from "node:fs";
import { join } from "node:path";
import { describe, expect, it } from "vitest";

/**
 * Purity guard: this package is the framework-free half of the performance
 * stack. A React, DOM or app import here would reappear in every consumer —
 * including the R5 Worker bundle, which cannot load React.
 */
describe("@digithings-ai/perf-math boundary", () => {
  it("stays free of React, DOM and app imports", () => {
    const dir = new URL(".", import.meta.url).pathname;
    const sources = readdirSync(dir).filter(
      (name) => name.endsWith(".ts") && !name.endsWith(".test.ts"),
    );
    expect(sources.length).toBeGreaterThan(0);
    for (const name of sources) {
      const text = readFileSync(join(dir, name), "utf8");
      expect(text, name).not.toMatch(/from\s+["']react(-dom)?["']/);
      expect(text, name).not.toMatch(/@digithings-ai\//);
      expect(text, name).not.toMatch(/@digiquant-io\//);
      expect(text, name).not.toMatch(/from\s+["']node:/);
    }
  });
});
