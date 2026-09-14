/**
 * Build the inline CSS custom-property style that overrides embed `--accent`.
 *
 * Kept pure (no React / window) so unit tests can pin the DataTap terracotta
 * regression: a validated hex must produce a style object React will serialize
 * onto the wrapper (`style="--accent:#b5562b"`), and an absent/invalid color
 * must yield `undefined` (React then omits the attribute — the bug symptom).
 */

import type { CSSProperties } from "react";

const HEX_COLOR = /^#[0-9a-fA-F]{6}$/;

export function isEmbedHexColor(raw: string | null | undefined): raw is string {
  return typeof raw === "string" && HEX_COLOR.test(raw);
}

export function buildEmbedAccentStyle(
  color?: string | null,
  foreground?: string | null,
): CSSProperties | undefined {
  if (!isEmbedHexColor(color)) return undefined;
  const style: Record<string, string> = { "--accent": color };
  if (isEmbedHexColor(foreground)) {
    style["--accent-foreground"] = foreground;
  }
  return style as CSSProperties;
}
