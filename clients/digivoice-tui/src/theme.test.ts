/**
 * The terminal palette is a restatement of the shared tokens, so it can drift.
 * This pins it: every text tone is the dark terminal token it claims to be, and
 * every text tone clears the 4.5:1 floor on the terminal ground.
 */
import { readFileSync } from "node:fs";
import { expect, test } from "bun:test";

import { ACCENT, BG, DANGER, INK, MUTE, SOFT, WARN } from "./theme";

const TOKENS = readFileSync(
  new URL("../../../packages/design/tokens.css", import.meta.url),
  "utf8",
);

/** The `:root[data-theme="dark"]` block, where the terminal register lives. */
const DARK = TOKENS.slice(
  TOKENS.indexOf(':root[data-theme="dark"]'),
  TOKENS.indexOf(':root[data-theme="light"]'),
);

function channel(value: number): number {
  const c = value / 255;
  return c <= 0.04045 ? c / 12.92 : ((c + 0.055) / 1.055) ** 2.4;
}

/** WCAG relative luminance of a `#rrggbb` colour. */
function luminance(hex: string): number {
  const h = hex.replace("#", "");
  const [r, g, b] = [0, 2, 4].map((i) => channel(parseInt(h.slice(i, i + 2), 16)));
  return 0.2126 * r + 0.7152 * g + 0.0722 * b;
}

/** WCAG contrast ratio between two `#rrggbb` colours. */
function contrast(a: string, b: string): number {
  const [hi, lo] = [luminance(a), luminance(b)].sort((x, y) => y - x);
  return (hi + 0.05) / (lo + 0.05);
}

test("the terminal text tones are the dark token values", () => {
  expect(DARK).toMatch(new RegExp(`--term-bg:\\s+${BG}`, "i"));
  expect(DARK).toMatch(new RegExp(`--term-ink:\\s+${INK}`, "i"));
  expect(DARK).toMatch(new RegExp(`--ink-soft:\\s+${SOFT}`, "i"));
  expect(DARK).toMatch(new RegExp(`--term-mute:\\s+${MUTE}`, "i"));
  expect(DARK).toMatch(new RegExp(`--accent:\\s+${ACCENT}`, "i"));
  expect(DARK).toMatch(new RegExp(`--warn:\\s+${WARN}`, "i"));
});

test("every text tone clears 4.5:1 on the terminal ground", () => {
  const tones = { INK, SOFT, MUTE, ACCENT, DANGER, WARN };
  for (const [name, hex] of Object.entries(tones)) {
    const ratio = contrast(hex, BG);
    expect(ratio, `${name} ${hex} on ${BG} is ${ratio.toFixed(2)}:1`).toBeGreaterThanOrEqual(4.5);
  }
});
