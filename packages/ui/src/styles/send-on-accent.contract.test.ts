import { readFileSync } from "node:fs";
import { join } from "node:path";
import { describe, expect, it } from "vitest";
import { PALETTES, PALETTE_IDS } from "../theme/palette-registry";

/**
 * The send arrow on the filled accent button: white in light mode whenever
 * white clears 3:1 against the accent (WCAG 1.4.11, icons), otherwise dark.
 * chat-aui.css picks it in CSS from the accent's OKLab lightness; this pins
 * that threshold against every palette so a palette change cannot silently
 * drop the arrow below 3:1.
 */
const css = readFileSync(join(__dirname, "chat-aui.css"), "utf8");
const THRESHOLD = Number(css.match(/oklch\(from var\(--accent\) clamp\(0, \(([\d.]+) - l\)/)?.[1]);

function srgbToLinear(hex: string): [number, number, number] {
  const n = hex.replace("#", "");
  return [0, 2, 4].map((i) => {
    const c = parseInt(n.slice(i, i + 2), 16) / 255;
    return c <= 0.04045 ? c / 12.92 : ((c + 0.055) / 1.055) ** 2.4;
  }) as [number, number, number];
}

function luminance(hex: string): number {
  const [r, g, b] = srgbToLinear(hex);
  return 0.2126 * r + 0.7152 * g + 0.0722 * b;
}

function oklabL(hex: string): number {
  const [r, g, b] = srgbToLinear(hex);
  const l = Math.cbrt(0.4122214708 * r + 0.5363325363 * g + 0.0514459929 * b);
  const m = Math.cbrt(0.2119034982 * r + 0.6806995451 * g + 0.1073969566 * b);
  const s = Math.cbrt(0.0883024619 * r + 0.2817188376 * g + 0.6299787005 * b);
  return 0.2104542553 * l + 0.793617785 * m - 0.0040720468 * s;
}

function contrast(a: string, b: string): number {
  const [hi, lo] = [luminance(a), luminance(b)].sort((x, y) => y - x) as [number, number];
  return (hi + 0.05) / (lo + 0.05);
}

describe("send arrow on the accent button", () => {
  it("styles the arrow from the theme token, white-on-accent in light mode", () => {
    expect(css).toMatch(/\.aui-composer-send\s*\{\s*--on-accent-icon:\s*var\(--on-accent\);/);
    expect(css).toMatch(/:root\[data-theme="light"\] \.aui-composer-send\s*\{\s*--on-accent-icon:\s*oklch\(from var\(--accent\)/);
    expect(css).toMatch(/\.aui-composer-send\.text-on-accent\s*\{\s*color:\s*var\(--on-accent-icon\);/);
    expect(THRESHOLD).toBeGreaterThan(0.6);
  });

  // Tenant accents ride the same rule; the tenant chat orange is the case
  // that prompted it.
  const accents: [string, string][] = [
    ...PALETTE_IDS.map((id) => [`${id} light`, PALETTES[id].light.accent] as [string, string]),
    ["tenant chat orange", "#F05F24"],
  ];

  it.each(accents)("keeps the light-mode arrow at 3:1 or better on %s", (_name, accent) => {
    const arrow = oklabL(accent) < THRESHOLD ? "#ffffff" : "#000000";
    expect(contrast(accent, arrow)).toBeGreaterThanOrEqual(3);
  });

  it("turns the arrow white on the orange accents", () => {
    for (const accent of ["#F05F24", PALETTES.orng.light.accent]) {
      expect(oklabL(accent)).toBeLessThan(THRESHOLD);
    }
  });

  it.each(PALETTE_IDS.map((id) => [id, PALETTES[id].dark] as const))(
    "keeps the dark-mode arrow on the palette's on-accent (%s)",
    (_id, dark) => {
      expect(contrast(dark.accent, dark.onAccent)).toBeGreaterThanOrEqual(3);
    },
  );
});
