/**
 * ui.js — small shared UI behaviours: sticky-nav glass, mobile nav toggle,
 * and copy-to-clipboard buttons. All progressive-enhancement; no-ops if the
 * expected elements are absent.
 */

/** Add `.is-stuck` to the nav once the page scrolls. */
export function initNav(navId = "nav", toggleId = "nav-toggle", linksId = "nav-links") {
  const nav = document.getElementById(navId);
  if (nav) {
    const onScroll = () => nav.classList.toggle("is-stuck", window.scrollY > 8);
    onScroll();
    addEventListener("scroll", onScroll, { passive: true });
  }

  const toggle = document.getElementById(toggleId);
  const links = document.getElementById(linksId);
  if (toggle && links) {
    const close = () => { toggle.setAttribute("aria-expanded", "false"); links.classList.remove("open"); };
    toggle.addEventListener("click", () => {
      const open = toggle.getAttribute("aria-expanded") === "true";
      toggle.setAttribute("aria-expanded", String(!open));
      links.classList.toggle("open", !open);
    });
    links.querySelectorAll("a").forEach((a) => a.addEventListener("click", close));
    addEventListener("keydown", (e) => { if (e.key === "Escape") close(); });
  }
}

/**
 * Wire copy buttons. Each button has [data-copy="<text>"] OR [data-copy-target="#sel"]
 * (copies that element's textContent). Shows a brief "copied" state.
 */
export function initCopy(selector = "[data-copy], [data-copy-target]") {
  document.querySelectorAll(selector).forEach((btn) => {
    btn.addEventListener("click", async () => {
      let text = btn.getAttribute("data-copy");
      const tgtSel = btn.getAttribute("data-copy-target");
      if (!text && tgtSel) {
        const t = document.querySelector(tgtSel);
        text = t ? t.textContent.trim() : "";
      }
      if (!text) return;
      try {
        await navigator.clipboard.writeText(text);
        const label = btn.querySelector("[data-copy-label]") || btn;
        const prev = label.textContent;
        btn.classList.add("ok");
        label.textContent = "copied";
        setTimeout(() => { btn.classList.remove("ok"); label.textContent = prev; }, 1500);
      } catch (_) {}
    });
  });
}
