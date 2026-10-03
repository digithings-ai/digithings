/** Web desk dark chrome.
 *  digiquant-web paints `bg-black` and overrides `--bg` / `--term-bg` to `#000`.
 *  Ink, mute, accent, and danger are the dark tokens. Hairlines are white at
 *  9% and 15% on that black, which a terminal cell has to store as hex.
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
export const DANGER = "#E94959";
export const HAIR = hairOnBlack(0.09);
export const HAIR_STRONG = hairOnBlack(0.15);
/** Desk wash: white at 5% on the black canvas (`--term-fill`). */
export const WASH = hairOnBlack(0.05);
