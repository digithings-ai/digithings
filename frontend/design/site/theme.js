/**
 * theme.js — light/dark theme controller for the redesign foundation.
 *
 * Companion to a pre-paint snippet that MUST run in <head> before CSS paint to
 * avoid a flash (it sets data-theme from localStorage('dt-theme') or the OS):
 *
 *   <script>try{var s=localStorage.getItem('dt-theme');
 *     document.documentElement.setAttribute('data-theme',
 *       s||(matchMedia('(prefers-color-scheme: light)').matches?'light':'dark'))}catch(e){}</script>
 *
 * initTheme() then wires the toggle button, persistence, OS-follow (until the
 * user chooses), and theme-aware asset swapping. Any element carrying
 * data-src-dark / data-src-light (e.g. the QR mark <img> and the favicon
 * <link>) gets its src/href swapped per theme — works for any site.
 */
const KEY = "dt-theme";

function swapAssets(theme) {
  const attr = theme === "light" ? "data-src-light" : "data-src-dark";
  document.querySelectorAll("[data-src-dark][data-src-light]").forEach((el) => {
    const val = el.getAttribute(attr);
    if (!val) return;
    if (el.tagName === "LINK") el.setAttribute("href", val);
    else el.setAttribute("src", val);
  });
}

export function applyTheme(theme) {
  document.documentElement.setAttribute("data-theme", theme);
  swapAssets(theme);
}

export function initTheme(toggleId = "theme-toggle") {
  const root = document.documentElement;
  // sync assets to whatever the pre-paint snippet resolved
  swapAssets(root.getAttribute("data-theme") || "dark");

  const btn = document.getElementById(toggleId);
  if (btn) {
    btn.addEventListener("click", () => {
      const next = root.getAttribute("data-theme") === "light" ? "dark" : "light";
      applyTheme(next);
      try { localStorage.setItem(KEY, next); } catch (e) {}
    });
  }

  // follow OS only while the user hasn't made an explicit choice
  const mq = matchMedia("(prefers-color-scheme: light)");
  mq.addEventListener("change", (e) => {
    try { if (localStorage.getItem(KEY)) return; } catch (_) {}
    applyTheme(e.matches ? "light" : "dark");
  });
}
