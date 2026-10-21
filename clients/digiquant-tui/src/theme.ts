import { DIGIQUANT_CHART } from "../../../packages/ui/src/components/finance-charts/chart-scale";
import { paletteColors } from "../../../packages/ui/src/theme/tui-colors";
import { detectTerminalDark, readTuiPrefs, resolveTuiMode } from "../../../packages/ui/src/theme/tui-prefs";

/** Web desk dark chrome.
 *  digiquant-web paints `bg-black` and overrides `--bg` / `--term-bg` to `#000`.
 *  Ink, mute, accent, and danger are the dark tokens. Hairlines are white at
 *  9% and 15% on that black, which a terminal cell has to store as hex.
 *  Up and down are the kit chart scale (the canon pair), not a second red.
 *  `default` keeps these hexes. A stored palette replaces them from the registry.
 */

export function hairOnBlack(alpha: number): string {
  const channel = Math.round(255 * alpha);
  const hex = channel.toString(16).padStart(2, "0").toUpperCase();
  return `#${hex}${hex}${hex}`;
}

const DEFAULTS = {
  bg: "#000000",
  ink: "#ECEEF0",
  soft: "#9AA0A6",
  mute: "#7D8389",
  accent: "#3DD6C4",
  danger: "#E94959",
};

export let BG = DEFAULTS.bg;
export let INK = DEFAULTS.ink;
export let SOFT = DEFAULTS.soft;
export let MUTE = DEFAULTS.mute;
export let ACCENT = DEFAULTS.accent;
export const UP = DIGIQUANT_CHART.candleUp;
export const DOWN = DIGIQUANT_CHART.candleDown;
export let DANGER = DEFAULTS.danger;
/** Design package `--warn` (dark). The amber the dashboard badge uses for stale. */
export const WARN = "#E0B341";
export let HAIR = hairOnBlack(0.09);
export let HAIR_STRONG = hairOnBlack(0.15);
/** Desk wash: white at 5% on the black canvas (`--term-fill`). */
export let WASH = hairOnBlack(0.05);

const DEFAULT_HAIR = HAIR;
const DEFAULT_HAIR_STRONG = HAIR_STRONG;
const DEFAULT_WASH = WASH;

export function applyStoredTheme(path?: string): void {
  const prefs = readTuiPrefs(path);
  const mode = resolveTuiMode(prefs.mode, detectTerminalDark());
  const next = paletteColors(prefs.palette, mode);
  BG = next?.bg ?? DEFAULTS.bg;
  INK = next?.ink ?? DEFAULTS.ink;
  SOFT = next?.soft ?? DEFAULTS.soft;
  MUTE = next?.mute ?? DEFAULTS.mute;
  ACCENT = next?.accent ?? DEFAULTS.accent;
  DANGER = next?.danger ?? DEFAULTS.danger;
  HAIR = next?.hair ?? DEFAULT_HAIR;
  HAIR_STRONG = next?.hair ?? DEFAULT_HAIR_STRONG;
  WASH = next?.surface ?? DEFAULT_WASH;
}
