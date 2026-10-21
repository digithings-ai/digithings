/**
 * digivoice terminal tokens. Same hexes as the shared design system
 * (packages/ui/DESIGN.md) terminal register: terminal-bg, terminal-ink,
 * ink-soft, ink-mute, phosphor-teal, loss, caution. One font config: Geist
 * Mono. The accent is phosphor teal, the voice/audio colour.
 * `default` keeps these. Another palette replaces them from the registry.
 */
import { paletteColors } from "../../../packages/ui/src/theme/tui-colors";
import { detectTerminalDark, readTuiPrefs, resolveTuiMode } from "../../../packages/ui/src/theme/tui-prefs";

const DEFAULTS = {
  bg: "#08090b",
  ink: "#e7eaec",
  soft: "#9aa0a6",
  mute: "#6b7177",
  hair: "#2a2e33",
  fill: "#101317",
  accent: "#3dd6c4",
  danger: "#e5533e",
};

export let BG = DEFAULTS.bg;
export let INK = DEFAULTS.ink;
export let SOFT = DEFAULTS.soft;
export let MUTE = DEFAULTS.mute;
export let HAIR = DEFAULTS.hair;
export let FILL = DEFAULTS.fill;
export let ACCENT = DEFAULTS.accent;
export let DANGER = DEFAULTS.danger;
export const WARN = "#e0b341";

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
  ACCENT = next?.accent ?? DEFAULTS.accent;
  DANGER = next?.danger ?? DEFAULTS.danger;
}

// ASCII Magic marks. No emoji: the direction is half-block ASCII and plain
// monospace glyphs.
export const CURSOR = "▶";
export const MARK = ">";
export const BULLET = "·";
export const SEP = "·";
export const ON = "on";
export const OFF = "off";
export const DOT_LEAD = ".";
