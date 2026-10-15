import { readFileSync } from "node:fs";
import { describe, expect, it } from "vitest";
import { HERO_FONT_FALLBACK, heroChartFontFamily } from "../../app/_chrome/QuantField";

describe("heroChartFontFamily", () => {
  it("passes the live computed stack through, so canvas axes use the loaded face", () => {
    const live =
      '"__Geist_Mono_abc123", "Geist Mono", ui-monospace, SFMono-Regular, Menlo, monospace';
    expect(heroChartFontFamily(live)).toBe(live);
  });

  it("falls back to the generic stack when there is no computed family", () => {
    expect(heroChartFontFamily("")).toBe(HERO_FONT_FALLBACK);
    expect(heroChartFontFamily(null)).toBe(HERO_FONT_FALLBACK);
    expect(heroChartFontFamily(undefined)).toBe(HERO_FONT_FALLBACK);
    expect(heroChartFontFamily("   ")).toBe(HERO_FONT_FALLBACK);
  });

  it("keeps the fallback generic-only, so a fallback read is honest about the face", () => {
    expect(HERO_FONT_FALLBACK).not.toContain("Geist");
  });
});

describe("QuantField wiring", () => {
  const src = readFileSync(new URL("../../app/_chrome/QuantField.tsx", import.meta.url), "utf8");

  it("reads the host computed family into the Vela theme instead of a hardcoded stack", () => {
    expect(src).toContain("heroChartFontFamily(getComputedStyle(host).fontFamily)");
    expect(src).toContain("fontFamily: HERO_FONT_FALLBACK");
  });

  it("puts font-mono on the chart host so the computed family is the loaded stack", () => {
    expect(src).toMatch(/className="hero-chart [^"]*font-mono[^"]*"/);
  });
});
