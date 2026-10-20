/**
 * WCAG 2 relative-luminance + contrast helpers for the devkit swatch
 * readout. Vendored (not imported) from
 * `packages/ui/src/styles/contrast.contract.test.ts` — that file is a
 * test module and cannot be a runtime dependency. Formula: sRGB
 * linearization, L = 0.2126R + 0.7152G + 0.0722B, ratio (L1+0.05)/(L2+0.05).
 *
 * NOTE: the linearization cutoff here is 0.04045, matching the canon
 * source (`contrast.contract.test.ts:87-92`) exactly — not the older
 * 0.03928 WCAG 2.0 figure.
 */

/** WCAG AA minimum contrast for normal text (matches repo AA_TEXT canon). */
export const CONTRAST_MINIMUM = 4.5;

function channel(c: number): number {
  const s = c / 255;
  return s <= 0.04045 ? s / 12.92 : Math.pow((s + 0.055) / 1.055, 2.4);
}

export function luminance([r, g, b]: [number, number, number]): number {
  return 0.2126 * channel(r) + 0.7152 * channel(g) + 0.0722 * channel(b);
}

function hexToRgb(hex: string): [number, number, number] {
  return [
    parseInt(hex.slice(1, 3), 16),
    parseInt(hex.slice(3, 5), 16),
    parseInt(hex.slice(5, 7), 16),
  ];
}

export function contrast(a: string, b: string): number {
  const [l1, l2] = [luminance(hexToRgb(a)), luminance(hexToRgb(b))].sort((x, y) => y - x);
  return (l1 + 0.05) / (l2 + 0.05);
}
