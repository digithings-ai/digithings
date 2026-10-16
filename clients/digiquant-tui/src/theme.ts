import { DIGIQUANT_CHART } from "../../../packages/ui/src/components/finance-charts/chart-scale";

/** Web desk dark chrome.
 *  digiquant-web paints `bg-black` and overrides `--bg` / `--term-bg` to `#000`.
 *  Ink, mute, accent, and danger are the dark tokens. Hairlines are white at
 *  9% and 15% on that black, which a terminal cell has to store as hex.
 *  Up and down are the kit chart scale (the canon pair), not a second red.
 */

export function hairOnBlack(alpha: number): string {
  const channel = Math.round(255 * alpha);
  const hex = channel.toString(16).padStart(2, "0").toUpperCase();
  return `#${hex}${hex}${hex}`;
}

export const BG = "#000000";
export const INK = "#ECEEF0";
export const SOFT = "#9AA0A6";
export const MUTE = "#7D8389";
export const ACCENT = "#3DD6C4";
export const UP = DIGIQUANT_CHART.candleUp;
export const DOWN = DIGIQUANT_CHART.candleDown;
export const DANGER = "#E94959";
/** Design package `--warn` (dark). The amber the dashboard badge uses for stale. */
export const WARN = "#E0B341";
export const HAIR = hairOnBlack(0.09);
export const HAIR_STRONG = hairOnBlack(0.15);
/** Desk wash: white at 5% on the black canvas (`--term-fill`). */
export const WASH = hairOnBlack(0.05);
