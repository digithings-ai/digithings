import { readFileSync } from "node:fs";
import path from "node:path";
import { describe, expect, it } from "vitest";

/**
 * Base-skin markdown links paint `text-accent`. Inside the shadcn `.dark`
 * block that token is the hover tint, so a link on a framed or catalog base
 * skin in dark mode sat at about 1.3:1 on the chat canvas. The bridge gives
 * the link its own --accent (the dark foreground). This pins that token and
 * holds it to WCAG AA (4.5:1) against the dark --background.
 */

const css = readFileSync(path.resolve(__dirname, "digichat-app-theme.css"), "utf8").replace(
  /\/\*[\s\S]*?\*\//g,
  "",
);

function darkToken(name: string): string {
  const block = css.match(/(?:^|\n)\.dark\s*\{([^}]*)\}/);
  expect(block, ".dark block in digichat-app-theme.css").toBeTruthy();
  const value = block![1].match(new RegExp(`${name}:\\s*([^;]+);`))?.[1]?.trim();
  expect(value, `.dark ${name}`).toBeDefined();
  return value!;
}

/** oklch(L C h) → relative luminance (WCAG), via OKLab → linear sRGB. */
function luminance(oklch: string): number {
  const m = oklch.match(/^oklch\(\s*([\d.]+)\s+([\d.]+)\s+([\d.]+)\s*\)$/);
  expect(m, `${oklch} is a plain oklch() colour`).toBeTruthy();
  const [L, C, H] = [Number(m![1]), Number(m![2]), (Number(m![3]) * Math.PI) / 180];
  const a = C * Math.cos(H);
  const b = C * Math.sin(H);
  const l = (L + 0.3963377774 * a + 0.2158037573 * b) ** 3;
  const mm = (L - 0.1055613458 * a - 0.0638541728 * b) ** 3;
  const s = (L - 0.0894841775 * a - 1.291485548 * b) ** 3;
  const clamp = (v: number) => Math.min(1, Math.max(0, v));
  const r = clamp(4.0767416621 * l - 3.3077115913 * mm + 0.2309699292 * s);
  const g = clamp(-1.2684380046 * l + 2.6097574011 * mm - 0.3413193965 * s);
  const bl = clamp(-0.0041960863 * l - 0.7034186147 * mm + 1.707614701 * s);
  return 0.2126 * r + 0.7152 * g + 0.0722 * bl;
}

function contrast(fg: string, bg: string): number {
  const [hi, lo] = [luminance(fg), luminance(bg)].sort((x, y) => y - x);
  return (hi + 0.05) / (lo + 0.05);
}

describe("base skin dark links", () => {
  const rule = css.match(/([^{}]*\.dark \.aui-md-a[^{}]*)\{([^}]*)\}/);

  it("the bridge gives dark markdown links their own --accent", () => {
    expect(rule, ".dark .aui-md-a rule in digichat-app-theme.css").toBeTruthy();
    expect(rule![2]).toMatch(/--accent:\s*var\(--foreground\)\s*;/);
  });

  it("covers a dark root and a dark wrapper, never a site chat (site theme, app mode)", () => {
    const selectors = rule![1].split(",").map((sel) => sel.trim());
    expect(selectors).toHaveLength(2);
    expect(selectors.some((sel) => sel.startsWith(":root.dark"))).toBe(true);
    for (const sel of selectors) {
      expect(sel).toMatch(/:not\(\[data-site-theme="1"\]\)/);
      expect(sel).toMatch(/:not\(:has\(\[data-chrome-mode="app"\]\)\)/);
    }
  });

  it("meets WCAG AA (4.5:1) on the dark chat background", () => {
    const ratio = contrast(darkToken("--foreground"), darkToken("--background"));
    expect(ratio).toBeGreaterThanOrEqual(4.5);
  });

  it("the shadcn dark --accent alone would fail AA (why the override exists)", () => {
    expect(contrast(darkToken("--accent"), darkToken("--background"))).toBeLessThan(4.5);
  });
});

/** #rrggbb → WCAG relative luminance. */
function hexLuminance(hex: string): number {
  const m = hex.match(/^#([0-9a-f]{2})([0-9a-f]{2})([0-9a-f]{2})$/i);
  expect(m, `${hex} is a #rrggbb colour`).toBeTruthy();
  const [r, g, b] = m!.slice(1).map((h) => {
    const c = parseInt(h, 16) / 255;
    return c <= 0.04045 ? c / 12.92 : ((c + 0.055) / 1.055) ** 2.4;
  });
  return 0.2126 * r + 0.7152 * g + 0.0722 * b;
}

/** #rrggbb → OKLCH hue in degrees. */
function hexHue(hex: string): number {
  const [r, g, b] = [1, 3, 5].map((i) => {
    const c = parseInt(hex.slice(i, i + 2), 16) / 255;
    return c <= 0.04045 ? c / 12.92 : ((c + 0.055) / 1.055) ** 2.4;
  });
  const l = Math.cbrt(0.4122214708 * r + 0.5363325363 * g + 0.0514459929 * b);
  const mm = Math.cbrt(0.2119034982 * r + 0.6806995451 * g + 0.1073969566 * b);
  const s = Math.cbrt(0.0883024619 * r + 0.2817188376 * g + 0.6299787005 * b);
  const a = 1.9779984951 * l - 2.428592205 * mm + 0.4505937099 * s;
  const bb = 0.0259040371 * l + 0.7827717662 * mm - 0.808675766 * s;
  return (Math.atan2(bb, a) * 180) / Math.PI;
}

function lightToken(name: string): string {
  const block = css.match(/(?:^|\n):root\s*\{([^}]*)\}/);
  expect(block, ":root block in digichat-app-theme.css").toBeTruthy();
  const value = block![1].match(new RegExp(`${name}:\\s*([^;]+);`))?.[1]?.trim();
  expect(value, `:root ${name}`).toBeDefined();
  return value!;
}

describe("base skin light links", () => {
  const DIGICHAT_PINK = "#e2708a";
  const rule = css.match(/([^{}]*:root:not\(\.dark\)[^{}]*\.aui-thread-root[^{}]*\.aui-md-a[^{}]*)\{([^}]*)\}/);
  const accent = rule?.[2].match(/--accent:\s*(#[0-9a-fA-F]{6})\s*;/)?.[1];

  it("the bridge gives light base-thread links their own --accent", () => {
    expect(rule, "light .aui-thread-root .aui-md-a rule in digichat-app-theme.css").toBeTruthy();
    expect(accent, "a #rrggbb --accent").toBeDefined();
  });

  it("is light-only, base-thread-only, never a site chat or app mode", () => {
    const sel = rule![1].trim();
    expect(sel.split(",")).toHaveLength(1);
    expect(sel).toMatch(/^:root:not\(\.dark\)/);
    expect(sel).toMatch(/\.aui-thread-root:not\(\.dark \*\) \.aui-md-a$/);
    expect(sel).toMatch(/:not\(\[data-site-theme="1"\]\)/);
    expect(sel).toMatch(/:not\(:has\(\[data-chrome-mode="app"\]\)\)/);
  });

  it("meets WCAG AA (4.5:1) on the light chat background", () => {
    expect(lightToken("--background")).toBe("oklch(1 0 0)");
    expect((1 + 0.05) / (hexLuminance(accent!) + 0.05)).toBeGreaterThanOrEqual(4.5);
  });

  it("stays in the digichat pink hue family (within 5 degrees of OKLCH hue)", () => {
    expect(Math.abs(hexHue(accent!) - hexHue(DIGICHAT_PINK))).toBeLessThanOrEqual(5);
  });

  it("the digichat pink alone would fail AA on white (why the override exists)", () => {
    expect((1 + 0.05) / (hexLuminance(DIGICHAT_PINK) + 0.05)).toBeLessThan(4.5);
  });
});
