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

/** What the document is painting right now (the pre-paint script or a pin set it). */
export function readPaintedTheme(
  doc: Document | null = typeof document === "undefined" ? null : document,
): { resolved: ResolvedTheme; palette: PaletteName } {
  const root = doc?.documentElement;
  return {
    resolved: root?.getAttribute("data-theme") === "light" ? "light" : "dark",
    palette: normalizePalette(root?.getAttribute("data-palette")),
  };
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

/**
 * Paint `data-theme` / `data-palette` and, for a user's choice, persist it.
 * Auto clears `dt-theme`; the default palette clears `dt-palette`. Pass
 * `{ persist: false }` to repaint without writing (an OS light/dark change).
 */
export function applyDocumentTheme(
  preference: ThemePreference,
  palette: string,
  doc: Document | null = typeof document === "undefined" ? null : document,
  options: { persist?: boolean } = {},
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
  const store = options.persist === false ? null : safeStorage();
  if (store && "setItem" in store) {
    const writable = store as Storage;
    writeKey(writable, THEME_STORAGE_KEY, preference === "auto" ? null : preference);
    writeKey(writable, PALETTE_STORAGE_KEY, pal === "default" ? null : pal);
  }
  if (doc) {
    try {
      doc.defaultView?.dispatchEvent(new Event(THEME_CHANGE_EVENT));
    } catch {
      /* ignore */
    }
  }
  return resolved;
}

/** One stop on the shared cycle: default dark, default light, then each palette in dark and light. */
export type ThemeStep = {
  id: string;
  label: string;
  mode: "dark" | "light";
  palette: PaletteName;
};

/** False when the palette's light block is its dark block (no light variant). */
export function hasLightVariant(id: PaletteId): boolean {
  const { light, dark } = PALETTES[id];
  return light.bg !== dark.bg;
}

/** Fired on window after every applyDocumentTheme, so a provider can re-read the document. */
export const THEME_CHANGE_EVENT = "dt-theme-change";

export function themeCycle(): readonly ThemeStep[] {
  const steps: ThemeStep[] = [
    { id: "default:dark", label: "default · dark", mode: "dark", palette: "default" },
    { id: "default:light", label: "default · light", mode: "light", palette: "default" },
  ];
  for (const id of PALETTE_IDS) {
    steps.push({ id: `${id}:dark`, label: `${id} · dark`, mode: "dark", palette: id });
    // A palette whose source registry has no distinct light variant
    // (catppuccin-frappe, catppuccin-macchiato) would paint its dark canvas
    // under the light chrome, so it offers dark only.
    if (hasLightVariant(id)) {
      steps.push({ id: `${id}:light`, label: `${id} · light`, mode: "light", palette: id });
    }
  }
  return steps;
}

/** The cycle stop that matches the painted mode and palette. Auto uses the resolved mode. */
export function matchThemeStep(
  preference: ThemePreference,
  palette: PaletteName,
  resolved: ResolvedTheme,
): ThemeStep {
  const mode = preference === "auto" ? resolved : preference;
  const steps = themeCycle();
  return steps.find((step) => step.mode === mode && step.palette === palette) ?? steps[0];
}

/** The next stop after the painted one. Wraps to default dark. */
export function nextThemeStep(
  preference: ThemePreference,
  palette: PaletteName,
  resolved: ResolvedTheme,
): ThemeStep {
  const steps = themeCycle();
  const current = matchThemeStep(preference, palette, resolved);
  const index = steps.findIndex((step) => step.id === current.id);
  return steps[(index + 1) % steps.length];
}

export { PALETTE_IDS, PALETTES, type PaletteId };
