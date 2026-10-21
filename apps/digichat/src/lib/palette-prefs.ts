/**
 * What the command palette is painting, and a deployment's palette default.
 *
 * A stored `dt-palette` is the user's choice and wins. When that key is
 * absent, a deployment palette paints `data-palette` without writing storage
 * and without touching `data-theme` (the dashboard and the theme boot script
 * own the mode).
 */

import {
  PALETTE_STORAGE_KEY,
  isPaletteId,
  readPaintedTheme,
  readThemeState,
  themeColorFor,
  type ThemeState,
} from "@digithings/ui/theme";

export function readEffectiveThemeState(): ThemeState {
  const state = readThemeState();
  if (typeof document === "undefined") return state;
  try {
    if (localStorage.getItem(PALETTE_STORAGE_KEY) != null) return state;
  } catch {
    return state;
  }
  return { ...state, palette: readPaintedTheme().palette };
}

/** Paint a deployment palette only when this browser has no palette choice. */
export function applyDeployedPalette(palette: string | null | undefined): void {
  if (typeof document === "undefined") return;
  try {
    if (localStorage.getItem(PALETTE_STORAGE_KEY) != null) return;
  } catch {
    return;
  }
  const id = (palette ?? "").trim().toLowerCase();
  if (!id || id === "default" || !isPaletteId(id)) return;
  const root = document.documentElement;
  root.setAttribute("data-palette", id);
  const resolved = root.getAttribute("data-theme") === "light" ? "light" : "dark";
  const meta = document.querySelector('meta[name="theme-color"]');
  if (meta) meta.setAttribute("content", themeColorFor(id, resolved));
}
