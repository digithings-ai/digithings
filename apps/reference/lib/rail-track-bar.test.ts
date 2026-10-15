import { readFileSync } from "node:fs";
import path from "node:path";
import { fileURLToPath } from "node:url";
import { describe, expect, it } from "vitest";

const APP = path.resolve(fileURLToPath(new URL(".", import.meta.url)), "..");
const REPO = path.resolve(APP, "../..");

const read = (rel: string) => readFileSync(path.join(APP, rel), "utf8");
const readKit = (rel: string) => readFileSync(path.join(REPO, "packages/ui/src", rel), "utf8");

/**
 * The three digiquant v2 promotions (plan section 6): each part has one
 * specimen on a gallery page that consumes the kit primitive (never a local
 * copy), and the kit barrel exports it. These are not `@digithings/ui/ui`
 * modules, so they are pinned here rather than in SPECIMENS.
 */
describe("HorizontalScrollTrack specimen", () => {
  const specimen = read("components/effects/horizontal-track-reference.tsx");

  it("consumes the kit track and stepper", () => {
    expect(specimen).toContain("HorizontalScrollTrack");
    expect(specimen).toContain("HorizontalTrackStepper");
    expect(specimen).toContain('from "@digithings/ui"');
  });

  it("is mounted on /effects with a jump-list entry", () => {
    const page = read("app/(gallery)/(motion)/effects/page.tsx");
    expect(page).toContain("<HorizontalTrackReference />");
    expect(page).toContain('id: "horizontal-track"');
  });

  it("is exported from the kit barrel", () => {
    const barrel = readKit("index.ts");
    for (const name of ["HorizontalScrollTrack", "HorizontalTrackStepper", "useHorizontalTrack"]) {
      expect(barrel, name).toContain(name);
    }
  });

  it("keeps the canon: no raw colour in the kit part, no motion.*, token stops in the mask", () => {
    const src = readKit("components/effects-chrome/HorizontalScrollTrack.tsx");
    expect(src).not.toMatch(/#[0-9a-fA-F]{3,8}\b/);
    expect(src).not.toMatch(/\bmotion\.(div|span|li)\b/);
    expect(src).toContain("var(--ink)");
  });
});

describe("CardRail specimen", () => {
  it("the changelog rail specimen is a thin consumer of the kit CardRail", () => {
    const specimen = read("components/changelog-rail-reference.tsx");
    expect(specimen).toContain("CardRail");
    expect(specimen).toContain('from "@digithings/ui"');
    expect(specimen).not.toContain("scrollBy");
    expect(specimen).not.toContain("cr-track");
  });

  it("the .cr-* family sheet is gone from the data page", () => {
    const css = read("app/(gallery)/(data-display)/data/data.css");
    expect(css).not.toContain(".cr-track");
    expect(css).not.toContain(".cr-arrow");
    expect(css).not.toContain(".cr-mask");
  });

  it("is exported from the kit barrel", () => {
    expect(readKit("index.ts")).toContain("CardRail");
  });
});

describe("MarketBar specimen", () => {
  const specimen = read("components/market-bar-reference.tsx");

  it("consumes the kit MarketBar next to the ticker specimen", () => {
    expect(specimen).toContain("MarketBar");
    expect(specimen).toContain('from "@digithings/ui"');
    const page = read("app/(gallery)/(finance)/finance/page.tsx");
    expect(page).toContain("<MarketBarReference />");
    expect(page.indexOf("<StockTickerReference />")).toBeLessThan(
      page.indexOf("<MarketBarReference />"),
    );
  });

  it("demonstrates every feed status and the empty state", () => {
    for (const status of ["connecting", "live", "stale", "offline"]) {
      expect(specimen, status).toContain(`"${status}"`);
    }
    expect(specimen).toContain("empty tape");
  });

  it("is exported from the kit barrel", () => {
    const barrel = readKit("index.ts");
    expect(barrel).toContain("MarketBar,");
    expect(barrel).toContain("MarketBarCell");
  });
});
