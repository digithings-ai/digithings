/**
 * Shared, persistent type-theme selection — the typographic sibling of
 * livery-store. A theme overrides `--font-display` and `--font-mono` inline on
 * <html> (the body face stays Geist Sans across all themes, so the comparison
 * isolates the display + mono choice — where the character lives). The choice
 * persists in localStorage and survives client navigation; the nav selector and
 * the Typography specimen both read it via useSyncExternalStore.
 *
 * "default" removes the overrides and falls back to the globals.css defaults
 * (Fraunces + Geist Mono). Fonts are loaded in app/layout.tsx via next/font.
 */

export type TypeTheme = { id: string; label: string; display: string; mono: string };

export const TYPE_THEMES: TypeTheme[] = [
  {
    id: "default",
    label: "default",
    display: "var(--font-fraunces), Georgia, serif",
    mono: "var(--font-geist-mono), ui-monospace, monospace",
  },
  {
    id: "instrument",
    label: "instrument",
    display: "var(--font-instrument), Georgia, serif",
    mono: "var(--font-geist-mono), ui-monospace, monospace",
  },
  {
    id: "newsreader",
    label: "newsreader",
    display: "var(--font-newsreader), Georgia, serif",
    mono: "var(--font-geist-mono), ui-monospace, monospace",
  },
  {
    id: "terminal",
    label: "terminal",
    display: "var(--font-jetbrains), ui-monospace, monospace",
    mono: "var(--font-jetbrains), ui-monospace, monospace",
  },
  {
    id: "bricolage",
    label: "bricolage",
    display: "var(--font-bricolage), system-ui, sans-serif",
    mono: "var(--font-geist-mono), ui-monospace, monospace",
  },
];

const KEY = "dr-type";
const EVENT = "dr-type-change";

/** Apply a type theme by overriding --font-display / --font-mono inline on
 *  <html>. Inline beats the `:root[data-theme]` declarations on the same
 *  element; "default" removes the overrides so the globals defaults win. */
export function applyType(id: string) {
  const el = document.documentElement;
  const t = TYPE_THEMES.find((x) => x.id === id);
  if (!t || id === "default") {
    el.style.removeProperty("--font-display");
    el.style.removeProperty("--font-mono");
  } else {
    el.style.setProperty("--font-display", t.display);
    el.style.setProperty("--font-mono", t.mono);
  }
  try {
    localStorage.setItem(KEY, id);
  } catch {
    /* private mode — non-fatal */
  }
  window.dispatchEvent(new CustomEvent(EVENT));
}

export function subscribeType(callback: () => void) {
  window.addEventListener(EVENT, callback);
  return () => window.removeEventListener(EVENT, callback);
}

export function getTypeSnapshot() {
  try {
    return localStorage.getItem(KEY) || "default";
  } catch {
    return "default";
  }
}

export function getTypeServerSnapshot() {
  return "default";
}

/** Pre-paint init: applies the stored type theme before first paint (no flash).
 *  The id→stack map is generated from TYPE_THEMES so there's one source. */
const MAP = Object.fromEntries(
  TYPE_THEMES.filter((t) => t.id !== "default").map((t) => [t.id, [t.display, t.mono]]),
);

export const typeInitScript = `(function(){try{var m=${JSON.stringify(MAP)};var v=localStorage.getItem('${KEY}');if(!v||v==='default')return;var t=m[v];if(!t)return;var el=document.documentElement;el.style.setProperty('--font-display',t[0]);el.style.setProperty('--font-mono',t[1]);}catch(e){}})();`;
