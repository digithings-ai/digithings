import { readFileSync } from "node:fs";
import { join } from "node:path";
import { renderToStaticMarkup } from "react-dom/server";
import { describe, expect, it } from "vitest";

import { preparedBanner } from "@digithings/hero-banner";
import { DIGICHAT } from "@digithings/hero-banner/definitions";

import { DigichatWordmark } from "./DigichatWordmark";
import * as React from "react";

// Test-env only: packages/hero-banner ships no tsconfig, so vitest compiles
// its web.tsx with classic JSX while production (Next.js) uses automatic.
// The free `React` name resolves here at render time.
(globalThis as unknown as Record<string, unknown>).React ??= React;

const SRC = readFileSync(join(__dirname, "DigichatWordmark.tsx"), "utf8");

describe("DigichatWordmark", () => {
  it("draws the shared DIGICHAT definition through HeroBanner", () => {
    expect(SRC).toContain("@digithings/hero-banner/definitions");
    expect(SRC).toContain("DIGICHAT");
    expect(SRC).toContain("@digithings/hero-banner/web");
    expect(SRC).toContain("HeroBanner");
    const html = renderToStaticMarkup(<DigichatWordmark />);
    expect(html).toContain('aria-label="digichat"');
    expect(html).toContain("<canvas");
  });

  it("keeps the shared grid off the definition, not a local copy", () => {
    const { layout } = preparedBanner(DIGICHAT);
    expect(layout.height).toBe(10);
    expect(layout.width).toBeGreaterThan(0);
    expect(SRC).not.toContain("heroWordmarkPixels");
  });
});
