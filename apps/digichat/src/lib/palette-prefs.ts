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
  THEME_STORAGE_KEY,
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
  // Store the mode alone first, then paint without persisting: dt-palette is
  // never written here, and the dt-theme-change event the paint dispatches
  // finds the new mode already in storage (ThemeProvider syncs from storage).
  try {
    if (preference === "auto") localStorage.removeItem(THEME_STORAGE_KEY);
    else localStorage.setItem(THEME_STORAGE_KEY, preference);
  } catch {
    /* no storage */
  }
  applyDocumentTheme(preference, state.palette, undefined, { persist: false });
}

/**
 * A valid stored palette choice, or null. An unknown or stale id is not a
 * choice (everywhere else it normalises to "default"), so it does not block
 * the deployment palette. Throws when storage is unreadable.
 */
function storedPaletteChoice(): string | null {
  const raw = localStorage.getItem(PALETTE_STORAGE_KEY)?.trim().toLowerCase() ?? null;
  return raw && (raw === "default" || isPaletteId(raw)) ? raw : null;
}

export function readEffectiveThemeState(): ThemeState {
  const state = readThemeState();
  if (typeof document === "undefined") return state;
  try {
    if (storedPaletteChoice() != null) return state;
  } catch {
    /* storage unreadable: what is painted is the truth */
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
    if (storedPaletteChoice() != null) return;
  } catch {
    /* storage unreadable: no stored choice, so the deployment default paints */
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
