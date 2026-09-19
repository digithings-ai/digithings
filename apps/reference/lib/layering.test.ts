import { readFileSync } from "node:fs";
import path from "node:path";
import { fileURLToPath } from "node:url";
import { describe, expect, it } from "vitest";

const APP = path.resolve(fileURLToPath(new URL(".", import.meta.url)), "..");

/**
 * Reference family sheets, all of which now put their dress in `@layer
 * components` so kit Tailwind utilities (in `utilities`) win on a tie — the
 * app-rebuild rule documented in packages/ui/MIGRATION.md. `(chatbot)` is a
 * second root that themes vendor assistant-ui styles and deliberately keeps
 * its own unlayered cascade.
 */
const LAYERED_SHEETS = [
  "app/(gallery)/(foundations)/home.css",
  "app/(gallery)/(pages)/(templates)/account/account.css",
  "app/(gallery)/(chrome)/chrome/chrome.css",
  "app/(gallery)/(data-display)/data/data.css",
  "app/(gallery)/(motion)/effects/effects.css",
  "app/(gallery)/(finance)/finance/finance.css",
  "app/(gallery)/(layout)/layout-patterns/layout.css",
  "app/(gallery)/(symbols)/symbols/symbols.css",
  "app/(gallery)/(typography)/typography/typography.css",
  "app/(gallery)/rtl/rtl.css",
  "app/(gallery)/(chat)/terminal/terminal.css",
] as const;

const CONTROLS_SHEET = "app/(gallery)/(controls)/controls/controls.css";

describe("reference family CSS layering", () => {
  for (const rel of LAYERED_SHEETS) {
    it(`${rel} wraps its dress in @layer components`, () => {
      const source = readFileSync(path.join(APP, rel), "utf8");
      expect(source).toMatch(/@layer components\s*\{/);
    });
  }

  it("terminal.css keeps its @import ahead of the layer", () => {
    const source = readFileSync(path.join(APP, "app/(gallery)/(chat)/terminal/terminal.css"), "utf8");
    const importAt = source.indexOf("@import");
    const layerAt = source.indexOf("@layer components");
    expect(importAt).toBeGreaterThanOrEqual(0);
    expect(layerAt).toBeGreaterThan(importAt);
  });

  it("controls.css layers its dress but keeps .sb-hint unlayered by design", () => {
    const source = readFileSync(path.join(APP, CONTROLS_SHEET), "utf8");
    const hintAt = source.indexOf(".sb-hint");
    const layerAt = source.indexOf("@layer components");
    expect(layerAt).toBeGreaterThanOrEqual(0);
    // The keycap hint must stay unlayered (it beats the unlayered `.kbd`) —
    // so it appears before the layer opens.
    expect(hintAt).toBeGreaterThanOrEqual(0);
    expect(hintAt).toBeLessThan(layerAt);
    expect(source).toMatch(/UNLAYERED BY DESIGN/);
  });
});
