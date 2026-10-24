/**
 * digivoice terminal tokens. Same hexes as the shared design system terminal
 * register (`packages/design/tokens.css` `:root[data-theme="dark"]`):
 * `--term-bg`, `--term-ink`, `--ink-soft`, `--term-mute`, the phosphor-teal
 * accent, loss and caution. One font config: Geist Mono. The accent is phosphor
 * teal, the voice/audio colour.
 */
export const BG = "#08090b";
export const INK = "#e7eaec";
export const SOFT = "#9aa0a6";
/** `--term-mute`. Was `#6b7177`, which measured 4.03:1 on `--term-bg` — below
 *  the 4.5:1 floor for terminal body text, and a value no token declares. */
export const MUTE = "#7e858b";
export const HAIR = "#2a2e33";
export const FILL = "#101317";
export const ACCENT = "#3dd6c4";
export const DANGER = "#e5533e";
export const WARN = "#e0b341";

// ASCII Magic marks. No emoji: the direction is half-block ASCII and plain
// monospace glyphs.
export const CURSOR = "▶";
export const MARK = ">";
export const BULLET = "·";
export const SEP = "·";
export const ON = "on";
export const OFF = "off";
export const DOT_LEAD = ".";
