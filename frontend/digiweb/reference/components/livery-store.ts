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
import { modules } from "@digithings/web";

export type LiveryOption = { id: string; label: string; hex: string };

// Monochrome is the default (black + white); color is opt-in per product.
// research/portfolio/execution are backend langgraph names, not colored products — they
// are intentionally absent (and their accent tokens collapse to ink anyway).
// The module list itself is derived from the single modules registry
// (@digithings/web, also what FeaturePickerReference and the architecture
// graph consume) rather than hand-maintained here — a prior version hardcoded
// 7 modules, omitting digismith/digiclaw/digibase (which do have real, ruled
// --accent-<module> tokens) while including digistore (a roadmap-tier module
// with no shipped surface), and FeaturePickerReference's own tour derived a
// THIRD, different 7 by slicing the registry — three "which modules get a
// color" lists that each disagreed with the others and with the real 11-entry
// registry. hex resolves through the CSS custom property (like "mono" already
// did) rather than duplicating the literal color here, so a re-ruled accent
// never needs updating in two places.
export const LIVERY_OPTIONS: LiveryOption[] = [
  { id: "mono", label: "monochrome", hex: "var(--ink)" },
  ...modules
    .filter((mod) => mod.tier !== "roadmap")
    .map((mod) => ({ id: mod.id, label: mod.name, hex: `var(--accent-${mod.id})` })),
];

const KEY = "dr-livery";
const EVENT = "dr-livery-change";

/**
 * Liveries whose --accent already resolves to --ink (so it flips light/dark
 * WITH the theme, same as the theme's own on-accent pairing). LIVERY_OPTIONS
 * only ever offers "mono" — research/portfolio/execution aren't selectable liveries —
 * but applyLivery()'s `id` parameter is a plain string, not narrowed to
 * LIVERY_OPTIONS' ids, and tokens.css's matching .accent-research/-portfolio/-execution
 * classes exclude themselves from the --on-accent override for the same
 * reason (see tokens.css). Keeping both lists in agreement here means a
 * future caller passing one of these three ids can't reintroduce the
 * white-on-light-accent bug --on-accent's fix (below) exists to prevent.
 */
function isInkCollapsingLivery(id: string): boolean {
  return id === "mono" || id === "research" || id === "portfolio" || id === "execution";
}

/** Apply a livery by overriding --accent inline on <html>. Inline style beats
 *  the theme's `:root[data-theme]` --accent declaration (which sits on the same
 *  element), and works pre-paint since documentElement exists in <head>.
 *
 *  --on-accent needs the same inline override, and for the same reason: it's
 *  the text color painted on top of --accent (.btn-primary etc.), declared
 *  theme-scoped only in tokens.css (white on dark, near-black on light) — a
 *  pairing that's only correct when --accent flips light/dark WITH the theme,
 *  which is true for mono/research/portfolio/execution (--accent: var(--ink)) but
 *  false for every per-module hex here: they're fixed, light-to-medium colors
 *  in both themes, so the theme-scoped --on-accent goes white-on-light-accent
 *  in light theme (near-illegible — the same .accent-<module> scoped-class
 *  bug tokens.css's own comment on those classes documents). Every
 *  non-ink-collapsing id pins --on-accent to the same #06110f those classes
 *  use (verified ≥5.21:1 against every module hex in LIVERY_OPTIONS); an
 *  ink-collapsing id clears the inline override so --on-accent falls back to
 *  the theme's own flip, which is correct for --ink. */
export function applyLivery(id: string) {
  const el = document.documentElement;
  el.style.setProperty("--accent", id === "mono" ? "var(--ink)" : `var(--accent-${id})`);
  if (isInkCollapsingLivery(id)) {
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
    if (!v || v === "default") return "mono";
    return LIVERY_OPTIONS.some((o) => o.id === v) ? v : "mono";
  } catch {
    return "mono";
  }
}

/** Server render (and first hydration frame) sees the monochrome default. */
export function getLiveryServerSnapshot() {
  return "mono";
}

/** Allowed livery ids for the pre-paint init script (kept in sync with
 *  LIVERY_OPTIONS — roadmap / unknown ids fall back to mono). */
const LIVERY_INIT_IDS = LIVERY_OPTIONS.map((o) => o.id);

/** Pre-paint init: applies the stored livery before first paint (no flash).
 *  Monochrome is the default, so a missing/legacy/unsupported value resolves
 *  to ink. Mirrors applyLivery()'s --on-accent handling (including
 *  isInkCollapsingLivery's mono/research/portfolio/execution list — inlined here
 *  since this runs as a raw pre-hydration <script>, not compiled TS) — see
 *  its doc comment. */
export const liveryInitScript = `(function(){try{var allowed=${JSON.stringify(LIVERY_INIT_IDS)};var v=localStorage.getItem('${KEY}');if(v==='default')v=null;if(!v||allowed.indexOf(v)<0)v='mono';var ink=(v==='mono'||v==='research'||v==='portfolio'||v==='execution');var el=document.documentElement;el.style.setProperty('--accent',v==='mono'?'var(--ink)':'var(--accent-'+v+')');if(ink){el.style.removeProperty('--on-accent')}else{el.style.setProperty('--on-accent','#06110f')}}catch(e){}})();`;
