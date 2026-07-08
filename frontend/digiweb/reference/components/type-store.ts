/**
 * Shared, persistent type-SUITE selection — the typographic sibling of
 * livery-store. Each suite is a coordinated trio (display + body + mono) chosen
 * to work together; picking one overrides `--font-display`, `--font-sans`, and
 * `--font-mono` inline on <html>, so the whole reference re-typesets — headline,
 * body, and data all move together, not just the headline. The choice persists
 * in localStorage and survives navigation; the nav selector and the Typography
 * specimen read it via useSyncExternalStore.
 *
 * "default" removes the overrides and falls back to the globals.css defaults.
 * Fonts are loaded in app/layout.tsx via next/font.
 */

export type TypeSuite = {
  id: string;
  label: string;
  note: string;
  display: string;
  body: string;
  mono: string;
};

const GEIST_SANS = "var(--font-geist-sans), system-ui, -apple-system, sans-serif";
const GEIST_MONO = "var(--font-geist-mono), ui-monospace, monospace";

export const TYPE_SUITES: TypeSuite[] = [
  {
    id: "default",
    label: "default",
    note: "Fraunces · Geist Sans · Geist Mono",
    display: "var(--font-fraunces), Georgia, serif",
    body: GEIST_SANS,
    mono: GEIST_MONO,
  },
  {
    id: "plex",
    label: "plex",
    note: "IBM Plex superfamily — serif · sans · mono",
    display: "var(--font-plex-serif), Georgia, serif",
    body: "var(--font-plex-sans), system-ui, sans-serif",
    mono: "var(--font-plex-mono), ui-monospace, monospace",
  },
  {
    id: "editorial",
    label: "editorial",
    note: "Newsreader display + text · Geist Mono",
    display: "var(--font-newsreader), Georgia, serif",
    body: "var(--font-newsreader), Georgia, serif",
    mono: GEIST_MONO,
  },
  {
    id: "grotesk",
    label: "grotesk",
    note: "Bricolage Grotesque · Geist Sans · Geist Mono",
    display: "var(--font-bricolage), system-ui, sans-serif",
    body: GEIST_SANS,
    mono: GEIST_MONO,
  },
  {
    id: "terminal",
    label: "terminal",
    note: "JetBrains Mono display + mono · Geist Sans",
    display: "var(--font-jetbrains), ui-monospace, monospace",
    body: GEIST_SANS,
    mono: "var(--font-jetbrains), ui-monospace, monospace",
  },
];

const KEY = "dr-type";
const EVENT = "dr-type-change";

/** Apply a type suite by overriding --font-display / --font-sans / --font-mono
 *  inline on <html>. "default" removes the overrides so the globals win. */
export function applyType(id: string) {
  const el = document.documentElement;
  const t = TYPE_SUITES.find((x) => x.id === id);
  if (!t || id === "default") {
    el.style.removeProperty("--font-display");
    el.style.removeProperty("--font-sans");
    el.style.removeProperty("--font-mono");
  } else {
    el.style.setProperty("--font-display", t.display);
    el.style.setProperty("--font-sans", t.body);
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

/** Pre-paint init: applies the stored suite before first paint (no flash).
 *  The id→[display, body, mono] map is generated from TYPE_SUITES (one source). */
const MAP = Object.fromEntries(
  TYPE_SUITES.filter((t) => t.id !== "default").map((t) => [t.id, [t.display, t.body, t.mono]]),
);

export const typeInitScript = `(function(){try{var m=${JSON.stringify(MAP)};var v=localStorage.getItem('${KEY}');if(!v||v==='default')return;var t=m[v];if(!t)return;var el=document.documentElement;el.style.setProperty('--font-display',t[0]);el.style.setProperty('--font-sans',t[1]);el.style.setProperty('--font-mono',t[2]);}catch(e){}})();`;
