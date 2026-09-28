/** User-facing direction copy — always lowercase (long / short, not LONG). */

export function directionLabel(direction: "long" | "short"): string {
  return direction;
}

export const LONG_SHORT_KIND = "long / short";
export const LONG_ONLY_KIND = "long only";
export const SHORT_ONLY_KIND = "short only";
