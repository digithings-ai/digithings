/**
 * Pre-paint scripts for the embed document.
 *
 * Every string here is a constant built from the palette registry and the
 * light/dark literal. Nothing from the request is concatenated in. The
 * scripts read `location` and `window.top` themselves.
 */
import { PALETTE_IDS } from "@digithings/ui/theme";

const THEME_LOCK = "/[?&]theme=(?:light|dark)(?:&|$)/";

/**
 * A top-level chat with no `?theme=` follows the site (`dt-theme` /
 * `dt-palette` already painted by `themeInitScript`). An iframe, or a URL
 * that names a theme, keeps the tenant/parent pin.
 */
export function embedDocumentFollowsSiteTheme(topLevel: boolean, search: string): boolean {
  return topLevel && !new RegExp(THEME_LOCK.slice(1, -1)).test(search);
}

const CANVAS: Record<"light" | "dark", string> = {
  light: "#f1f0eb",
  dark: "#121417",
};

/** Pin script for one mode. The other branch leaves the site paint alone. */
export function themePinScript(theme: "dark" | "light"): string {
  const other = theme === "light" ? "dark" : "light";
  const color = CANVAS[theme];
  return (
    "try{var top=false;try{top=window.top===window}catch(e){}" +
    `var locked=${THEME_LOCK}.test(location.search);var e=document.documentElement;` +
    "if(top&&!locked){e.setAttribute('data-site-theme','1');e.removeAttribute('data-theme-pin')}" +
    `else{e.setAttribute('data-theme','${theme}');e.setAttribute('data-theme-pin','1');` +
    "e.removeAttribute('data-palette');e.removeAttribute('data-site-theme');" +
    `e.classList.add('${theme}');e.classList.remove('${other}');` +
    "var m=document.querySelector('meta[name=theme-color]');if(!m){m=document.createElement('meta');" +
    "m.setAttribute('name','theme-color');document.head.appendChild(m)}" +
    `m.setAttribute('content','${color}')}}catch(t){}`
  );
}

/** When the document is pinned, adopt an allowlisted `?palette=` before paint. */
export function embedPalettePinScript(): string {
  const ids = JSON.stringify(PALETTE_IDS);
  return (
    "try{var e=document.documentElement;if(e.getAttribute('data-theme-pin')!=='1'){/* site-owned */}" +
    "else{var p=new URLSearchParams(location.search).get('palette');" +
    `if(p){p=p.toLowerCase();var ok=${ids};if(ok.indexOf(p)!==-1)e.setAttribute('data-palette',p)}}}catch(err){}`
  );
}

/** Rails on a top-level chat document. An iframe keeps the parent's rails. */
export const SITE_RAILS_SCRIPT =
  "try{var top=false;try{top=window.top===window}catch(e){}document.documentElement.setAttribute('data-site-rails',top?'1':'0')}catch(e){}";

/** Beats the embed's per-mode canvas hex when the document follows the site. */
export const SITE_EMBED_CANVAS_CSS =
  ':root[data-site-theme="1"][data-theme="dark"],:root[data-site-theme="1"][data-theme="light"]{--embed-canvas:var(--bg)}';
