/** Dark digichat thread tokens. Same hexes as `.digichat-thread` in chat-aui.css.
 *  `default` keeps these. Another palette replaces them from the registry.
 */
import { paletteColors } from "../../../packages/ui/src/theme/tui-colors";
import { detectTerminalDark, readTuiPrefs, resolveTuiMode } from "../../../packages/ui/src/theme/tui-prefs";

const DEFAULTS = {
  bg: "#08090b",
  ink: "#eceef0",
  soft: "#9aa0a6",
  mute: "#7e858b",
  hair: "#2a2e33",
  fill: "#101317",
  danger: "#e5533e",
};

export let BG = DEFAULTS.bg;
export let INK = DEFAULTS.ink;
export let SOFT = DEFAULTS.soft;
export let MUTE = DEFAULTS.mute;
export let HAIR = DEFAULTS.hair;
export let FILL = DEFAULTS.fill;

/** Danger from `.digichat-thread` (`--danger`). */
export let DANGER = DEFAULTS.danger;

export function applyStoredTheme(path?: string): void {
  const prefs = readTuiPrefs(path);
  const mode = resolveTuiMode(prefs.mode, detectTerminalDark());
  const next = paletteColors(prefs.palette, mode);
  BG = next?.bg ?? DEFAULTS.bg;
  INK = next?.ink ?? DEFAULTS.ink;
  SOFT = next?.soft ?? DEFAULTS.soft;
  MUTE = next?.mute ?? DEFAULTS.mute;
  HAIR = next?.hair ?? DEFAULTS.hair;
  FILL = next?.surface ?? DEFAULTS.fill;
  DANGER = next?.danger ?? DEFAULTS.danger;
}

/**
 * Glyphs the web draws as 5×5 cubes. A terminal cell cannot hold that matrix,
 * so each control keeps the cube's meaning: plus, arrow, stop, chevron.
 */
export const USER_MARK = ">";
export const NEW_CHAT = "+";
export const ATTACH = "+";
export const SEND = "↑";
export const STOP = "■";
export const VOICE = "mic";
export const SCROLL = "↓";
export const EXPAND = ">";
export const EXPANDED = "v";
export const EXAMPLE = "◆";
