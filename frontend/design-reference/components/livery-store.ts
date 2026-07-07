/**
 * Shared, persistent livery selection for the whole reference. The chosen
 * livery drives `--accent` on <html>, so every unscoped component re-dresses
 * and the choice survives client navigation (the <html> element persists).
 * State lives in localStorage + a custom event; both the nav control and the
 * Foundations theme gallery read it via useSyncExternalStore.
 *
 * "default" leaves the theme's own accent; "mono" is the umbrella treatment
 * (accent collapses to ink). Per-section `accent-*` scopes still win locally.
 */

export type LiveryOption = { id: string; label: string; hex: string };

export const LIVERY_OPTIONS: LiveryOption[] = [
  { id: "default", label: "default", hex: "var(--accent)" },
  { id: "mono", label: "monochrome", hex: "var(--ink)" },
  { id: "digigraph", label: "digigraph", hex: "#e5b765" },
  { id: "digiquant", label: "digiquant", hex: "#3dd6c4" },
  { id: "digisearch", label: "digisearch", hex: "#5aa3c4" },
  { id: "digichat", label: "digichat", hex: "#e2708a" },
  { id: "digikey", label: "digikey", hex: "#d97a5a" },
  { id: "digivault", label: "digivault", hex: "#9d8fc9" },
  { id: "digistore", label: "digistore", hex: "#7b7fc7" },
  { id: "atlas", label: "atlas", hex: "#6fbf94" },
  { id: "hermes", label: "hermes", hex: "#4a8f7b" },
  { id: "kairos", label: "kairos", hex: "#2f7a65" },
];

const KEY = "dr-livery";
const EVENT = "dr-livery-change";

/** Apply a livery by overriding --accent inline on <html>. Inline style beats
 *  the theme's `:root[data-theme]` --accent declaration (which sits on the same
 *  element), and works pre-paint since documentElement exists in <head>. */
export function applyLivery(id: string) {
  const el = document.documentElement;
  if (id === "mono") el.style.setProperty("--accent", "var(--ink)");
  else if (id !== "default") el.style.setProperty("--accent", `var(--accent-${id})`);
  else el.style.removeProperty("--accent");
  try {
    localStorage.setItem(KEY, id);
  } catch {
    /* private mode — non-fatal */
  }
  window.dispatchEvent(new CustomEvent(EVENT));
}

export function subscribeLivery(callback: () => void) {
  window.addEventListener(EVENT, callback);
  return () => window.removeEventListener(EVENT, callback);
}

export function getLiverySnapshot() {
  try {
    return localStorage.getItem(KEY) || "default";
  } catch {
    return "default";
  }
}

/** Server render (and first hydration frame) always sees the default. */
export function getLiveryServerSnapshot() {
  return "default";
}

/** Pre-paint init: applies the stored livery before first paint (no flash). */
export const liveryInitScript = `(function(){try{var v=localStorage.getItem('${KEY}');if(!v||v==='default')return;var el=document.documentElement;el.style.setProperty('--accent',v==='mono'?'var(--ink)':'var(--accent-'+v+')')}catch(e){}})();`;
