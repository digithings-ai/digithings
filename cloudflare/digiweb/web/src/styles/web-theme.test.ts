import { readFileSync } from "node:fs";
import path from "node:path";
import { describe, expect, it } from "vitest";

// Single `__dirname` usage: the tsconfig carries no node types, so this file
// already reports TS2304 for it (pre-existing, like its node: imports).
const here = __dirname;

const css = readFileSync(path.resolve(here, "web-theme.css"), "utf8");

// The hair tokens are defined per [data-theme] block in the design package;
// the web-theme bridge only maps them to utilities. Pin the escalation alias
// where the other hair tokens actually live.
const tokens = readFileSync(
  path.resolve(here, "../../../design/tokens.css"),
  "utf8",
);

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
      ["--color-destructive", "var(--down)"],
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

describe("web-theme overlay contract", () => {
  it("declares the shared data-open/data-closed variants exactly once", () => {
    const variants = [
      '@custom-variant data-open (&:where([data-state="open"], [data-open]:not([data-open="false"])));',
      '@custom-variant data-closed (&:where([data-state="closed"], [data-closed]:not([data-closed="false"])));',
    ];
    for (const declaration of variants) {
      expect(css.split(declaration).length - 1).toBe(1);
    }
  });

  it("carries the collapsible keyframes with the Base UI panel-height fallback", () => {
    for (const name of ["collapsible-down", "collapsible-up"]) {
      expect(css.match(new RegExp(`@keyframes ${name}\\b`, "g"))?.length).toBe(1);
    }
    const fallback =
      "var(--radix-collapsible-content-height, var(--collapsible-panel-height, auto))";
    expect(css.split(fallback).length - 1).toBe(2);
  });
});

describe("hair scale contract (design/tokens.css)", () => {
  it("defines --hair-strong once per theme block as the --hair-2 escalation", () => {
    const dark = tokens.slice(
      tokens.indexOf(':root[data-theme="dark"]'),
      tokens.indexOf(':root[data-theme="light"]'),
    );
    const light = tokens.slice(tokens.indexOf(':root[data-theme="light"]'));
    for (const block of [dark, light]) {
      expect(block).toContain("--hair-strong: var(--hair-2);");
    }
    expect(tokens.match(/--hair-strong:/g)?.length).toBe(2);
  });
});
