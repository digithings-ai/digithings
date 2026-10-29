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
