/**
 * Platform theme: mode (`dt-theme`) and palette (`dt-palette`).
 *
 * `dt-theme` stores only `light` or `dark`. Auto removes the key so the OS
 * preference applies and live-updates. The dashboard writes the same key with
 * the resolved light/dark value and never touches `dt-palette`.
 */
import { PALETTE_IDS, PALETTES, type PaletteId } from "./palette-registry";

export const THEME_STORAGE_KEY = "dt-theme";
export const PALETTE_STORAGE_KEY = "dt-palette";

export type ThemePreference = "light" | "dark" | "auto";
export type ResolvedTheme = "light" | "dark";
export type PaletteName = PaletteId | "default";

/** Default canvas, matching tokens.css `--bg`. Read by `<meta name="theme-color">`. */
export const DEFAULT_THEME_COLOR: Record<ResolvedTheme, string> = {
  light: "#FBFBF9", // canon-allow: default --bg for the browser theme-color meta
  dark: "#0A0E0C", // canon-allow: default --bg for the browser theme-color meta
};

export function isPaletteId(value: string): value is PaletteId {
  return (PALETTE_IDS as readonly string[]).includes(value);
}

export function isThemePreference(value: string): value is ThemePreference {
  return value === "light" || value === "dark" || value === "auto";
}

export function normalizePalette(value: string | null | undefined): PaletteName {
  if (!value) return "default";
  const id = value.trim().toLowerCase();
  if (id === "default") return "default";
  return isPaletteId(id) ? id : "default";
}

type GetItem = { getItem(key: string): string | null };

function safeStorage(): GetItem | null {
  try {
    if (typeof localStorage === "undefined") return null;
    return localStorage;
  } catch {
    return null;
  }
}

export function readPreference(storage: GetItem | null): ThemePreference {
  if (!storage) return "auto";
  try {
    const raw = storage.getItem(THEME_STORAGE_KEY);
    if (raw === "light" || raw === "dark") return raw;
  } catch {
    /* private mode */
  }
  return "auto";
}

export function readPalette(storage: GetItem | null): PaletteName {
  if (!storage) return "default";
  try {
    return normalizePalette(storage.getItem(PALETTE_STORAGE_KEY));
  } catch {
    return "default";
  }
}

export function resolveTheme(preference: ThemePreference, prefersLight: boolean): ResolvedTheme {
  if (preference === "light" || preference === "dark") return preference;
  return prefersLight ? "light" : "dark";
}

export function themeColorFor(palette: string, resolved: ResolvedTheme): string {
  const id = normalizePalette(palette);
  if (id === "default") return DEFAULT_THEME_COLOR[resolved];
  return PALETTES[id][resolved].bg;
}

export type ThemeState = {
  preference: ThemePreference;
  palette: PaletteName;
  resolved: ResolvedTheme;
};

function prefersLightNow(): boolean {
  if (typeof matchMedia !== "function") return false;
  try {
    return matchMedia("(prefers-color-scheme: light)").matches;
  } catch {
    return false;
  }
}

export function readThemeState(storage?: GetItem | null, prefersLight?: boolean): ThemeState {
  const store = storage === undefined ? safeStorage() : storage;
  const preference = readPreference(store);
  const palette = readPalette(store);
  const resolved = resolveTheme(preference, prefersLight ?? prefersLightNow());
  return { preference, palette, resolved };
}

function writeKey(storage: Storage, key: string, value: string | null): void {
  try {
    if (value === null) storage.removeItem(key);
    else storage.setItem(key, value);
  } catch {
    /* ignore */
  }
}

/** Paint `data-theme` / `data-palette` and persist. Auto clears `dt-theme` only. */
export function applyDocumentTheme(
  preference: ThemePreference,
  palette: string,
  doc: Document | null = typeof document === "undefined" ? null : document,
): ResolvedTheme {
  const pal = normalizePalette(palette);
  const resolved = resolveTheme(preference, prefersLightNow());
  if (doc) {
    const root = doc.documentElement;
    root.setAttribute("data-theme", resolved);
    if (pal === "default") root.removeAttribute("data-palette");
    else root.setAttribute("data-palette", pal);
    try {
      let meta = doc.querySelector('meta[name="theme-color"]');
      if (!meta) {
        meta = doc.createElement("meta");
        meta.setAttribute("name", "theme-color");
        doc.head.appendChild(meta);
      }
      meta.setAttribute("content", themeColorFor(pal, resolved));
    } catch {
      /* ignore */
    }
  }
  const store = safeStorage();
  if (store && "setItem" in store) {
    const writable = store as Storage;
    writeKey(writable, THEME_STORAGE_KEY, preference === "auto" ? null : preference);
    writeKey(writable, PALETTE_STORAGE_KEY, pal === "default" ? null : pal);
  }
  return resolved;
}

export { PALETTE_IDS, PALETTES, type PaletteId };
