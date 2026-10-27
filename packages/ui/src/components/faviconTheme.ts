/**
 * Swap the tab icon to the painted theme.
 *
 * `prefers-color-scheme` on `<link rel="icon">` follows the OS, not the
 * site's `data-theme`. An SVG favicon also cannot read the page's theme.
 * This script runs after the theme init and again whenever `data-theme`
 * changes, and it rewrites the icon links the document already has.
 *
 * Baked light and dark files are required: a favicon does not inherit
 * `currentColor` from the page.
 */

export type FaviconThemePaths = {
  dark: string;
  light: string;
  touchDark: string;
  touchLight: string;
};

export function faviconThemeScript(paths: FaviconThemePaths): string {
  const spec = JSON.stringify(paths);
  return `try{var P=${spec};function applyFavicon(){var light=document.documentElement.getAttribute("data-theme")==="light";var icon=light?P.light:P.dark;var touch=light?P.touchLight:P.touchDark;document.querySelectorAll('link[rel="icon"],link[rel="shortcut icon"]').forEach(function(el){var type=el.getAttribute("type")||"";var href=el.getAttribute("href")||"";if(type==="image/svg+xml"||href.indexOf(".svg")!==-1){el.removeAttribute("media");el.setAttribute("href",icon);}});document.querySelectorAll('link[rel="apple-touch-icon"]').forEach(function(el){el.removeAttribute("media");el.setAttribute("href",touch);});}applyFavicon();new MutationObserver(applyFavicon).observe(document.documentElement,{attributes:true,attributeFilter:["data-theme"]});if(document.head){new MutationObserver(applyFavicon).observe(document.head,{childList:true});}}catch(e){}`;
}
