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
  THEME_CHANGE_EVENT,
  applyDocumentTheme,
  isPaletteId,
  readPaintedTheme,
  readThemeState,
  themeColorFor,
  type ThemePreference,
  type ThemeState,
} from "@digithings/ui/theme";

/**
 * `/theme light|dark|auto`: change the mode and keep the painted palette. A
 * palette the deployment painted is not the user's choice, so it is not
 * written to `dt-palette` (that would freeze the deployment default).
 */
export function applyThemeModeKeepingPalette(preference: ThemePreference): void {
  const state = readEffectiveThemeState();
  let storedPalette: string | null = null;
  try {
    storedPalette = localStorage.getItem(PALETTE_STORAGE_KEY);
  } catch {
    /* no storage */
  }
  applyDocumentTheme(preference, state.palette);
  if (storedPalette == null) {
    try {
      localStorage.removeItem(PALETTE_STORAGE_KEY);
    } catch {
      /* no storage */
    }
  }
}

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
  // A pinned embed owns its document (the pin removes data-palette and sets
  // the embed canvas theme-color); a deployment default must not repaint it.
  if (document.documentElement.getAttribute("data-theme-pin") === "1") return;
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
  // Let ThemeProvider re-read the painted palette (it syncs only on this event).
  try {
    window.dispatchEvent(new Event(THEME_CHANGE_EVENT));
  } catch {
    /* ignore */
  }
}
