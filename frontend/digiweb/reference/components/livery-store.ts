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
 *  element), and works pre-paint since documentElement exists in <head>.
 *
 *  --on-accent needs the same inline override, and for the same reason: it's
 *  the text color painted on top of --accent (.btn-primary etc.), declared
 *  theme-scoped only in tokens.css (white on dark, near-black on light) — a
 *  pairing that's only correct when --accent flips light/dark WITH the theme,
 *  which is true for mono (--accent: var(--ink)) but false for every
 *  per-module hex here: they're fixed, light-to-medium colors in both themes,
 *  so the theme-scoped --on-accent goes white-on-light-accent in light theme
 *  (near-illegible — the same .accent-<module> scoped-class bug tokens.css's
 *  own comment on those classes documents). Every id here except "mono" pins
 *  --on-accent to the same #06110f those classes use (verified ≥5.21:1
 *  against every module hex in LIVERY_OPTIONS); "mono" clears the inline
 *  override so --on-accent falls back to the theme's own flip, which is
 *  correct for --ink. */
export function applyLivery(id: string) {
  const el = document.documentElement;
  el.style.setProperty("--accent", id === "mono" ? "var(--ink)" : `var(--accent-${id})`);
  if (id === "mono") {
    el.style.removeProperty("--on-accent");
  } else {
    el.style.setProperty("--on-accent", "#06110f");
  }
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
 *  Monochrome is the default, so a missing/legacy value resolves to ink.
 *  Mirrors applyLivery()'s --on-accent handling — see its doc comment. */
export const liveryInitScript = `(function(){try{var v=localStorage.getItem('${KEY}');if(v==='default')v=null;v=v||'mono';var el=document.documentElement;el.style.setProperty('--accent',v==='mono'?'var(--ink)':'var(--accent-'+v+')');if(v==='mono'){el.style.removeProperty('--on-accent')}else{el.style.setProperty('--on-accent','#06110f')}}catch(e){}})();`;
