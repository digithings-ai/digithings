/**
 * Terminal colours for one palette. `null` means the caller's hardcoded
 * default (the look tests already pin).
 */
import { PALETTES, type PaletteId } from "./palette-registry";
import type { PaletteName } from "./apply-theme";

export type TuiColorSet = {
  bg: string;
  surface: string;
  ink: string;
  soft: string;
  mute: string;
  hair: string;
  accent: string;
  danger: string;
};

export function paletteColors(palette: PaletteName, mode: "light" | "dark"): TuiColorSet | null {
  if (palette === "default") return null;
  const row = PALETTES[palette as PaletteId][mode];
  return {
    bg: row.bg,
    surface: row.surface,
    ink: row.ink,
    soft: row.inkSoft,
    mute: row.inkMute,
    hair: row.hair,
    accent: row.accent,
    danger: row.danger,
  };
}
