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

// Monochrome is the default (black + white); color is opt-in per product.
// atlas/hermes/kairos are backend langgraph names, not colored products — they
// are intentionally absent (and their accent tokens collapse to ink anyway).
export const LIVERY_OPTIONS: LiveryOption[] = [
  { id: "mono", label: "monochrome", hex: "var(--ink)" },
  { id: "digigraph", label: "digigraph", hex: "#e5b765" },
  { id: "digiquant", label: "digiquant", hex: "#3dd6c4" },
  { id: "digisearch", label: "digisearch", hex: "#5aa3c4" },
  { id: "digichat", label: "digichat", hex: "#e2708a" },
  { id: "digikey", label: "digikey", hex: "#d97a5a" },
  { id: "digivault", label: "digivault", hex: "#9d8fc9" },
  { id: "digistore", label: "digistore", hex: "#7b7fc7" },
];

const KEY = "dr-livery";
const EVENT = "dr-livery-change";

/** Apply a livery by overriding --accent inline on <html>. Inline style beats
 *  the theme's `:root[data-theme]` --accent declaration (which sits on the same
 *  element), and works pre-paint since documentElement exists in <head>. */
export function applyLivery(id: string) {
  const el = document.documentElement;
  el.style.setProperty("--accent", id === "mono" ? "var(--ink)" : `var(--accent-${id})`);
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
    const v = localStorage.getItem(KEY);
    // migrate the retired "default" (theme cyan) selection to monochrome
    return !v || v === "default" ? "mono" : v;
  } catch {
    return "mono";
  }
}

/** Server render (and first hydration frame) sees the monochrome default. */
export function getLiveryServerSnapshot() {
  return "mono";
}

/** Pre-paint init: applies the stored livery before first paint (no flash).
 *  Monochrome is the default, so a missing/legacy value resolves to ink. */
export const liveryInitScript = `(function(){try{var v=localStorage.getItem('${KEY}');if(v==='default')v=null;v=v||'mono';var el=document.documentElement;el.style.setProperty('--accent',v==='mono'?'var(--ink)':'var(--accent-'+v+')')}catch(e){}})();`;
