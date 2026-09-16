import { readFileSync } from "node:fs";
import path from "node:path";
import { describe, expect, it } from "vitest";

const css = readFileSync(path.resolve(__dirname, "web-theme.css"), "utf8");

const chartNames = [
  "--color-chart-1",
  "--color-chart-2",
  "--color-chart-3",
  "--color-chart-4",
  "--color-chart-5",
];

const radiusNames = ["--radius-sm", "--radius-md", "--radius-lg", "--radius-xl"];

describe("web-theme shadcn token contract", () => {
  it("maps every shadcn token onto design tokens", () => {
    const pairs: [string, string][] = [
      ["--color-background", "var(--bg)"],
      ["--color-foreground", "var(--ink)"],
      ["--color-card", "var(--surface)"],
      ["--color-card-foreground", "var(--ink)"],
      ["--color-popover", "var(--surface-2)"],
      ["--color-popover-foreground", "var(--ink)"],
      ["--color-primary", "var(--ink)"],
      ["--color-primary-foreground", "var(--bg)"],
      ["--color-secondary", "var(--surface-2)"],
      ["--color-secondary-foreground", "var(--ink)"],
      ["--color-muted", "var(--surface)"],
      ["--color-muted-foreground", "var(--ink-soft)"],
      ["--color-accent", "var(--accent)"],
      ["--color-accent-foreground", "var(--on-accent)"],
      ["--color-destructive", "var(--danger)"],
      ["--color-border", "var(--hair)"],
      ["--color-input", "var(--hair)"],
      ["--color-ring", "color-mix(in srgb, var(--accent) 40%, transparent)"],
      ["--color-input-background", "var(--surface)"],
    ];
    const contractNames = [
      ...pairs.map(([name]) => name),
      ...chartNames,
      ...radiusNames,
    ];
    for (const name of contractNames) {
      expect(css.match(new RegExp(`${name}\\s*:`, "g"))?.length).toBe(1);
    }
    for (const [name, value] of pairs) {
      expect(css).toContain(`${name}: ${value};`);
    }
  });

  it("flattens shadcn radii to zero (Instrument Panel law)", () => {
    for (const radius of radiusNames) {
      expect(css).toContain(`${radius}: 0;`);
    }
  });

  it("keeps exactly one @theme block (canon)", () => {
    expect(css.match(/@theme\s+inline\s*\{/g)?.length).toBe(1);
  });
});
