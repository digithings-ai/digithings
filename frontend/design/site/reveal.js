/**
 * reveal.js — scroll reveal for `.reveal` elements with per-grid stagger.
 * Falls back to immediately visible under reduced-motion or no IntersectionObserver.
 */
export function initReveal(selector = ".reveal") {
  const els = document.querySelectorAll(selector);
  const reduce = matchMedia("(prefers-reduced-motion: reduce)").matches;
  if (reduce || !("IntersectionObserver" in window)) {
    els.forEach((el) => el.classList.add("in"));
    return;
  }
  // stagger siblings inside the same grid/principles container
  document.querySelectorAll(".grid, .principles").forEach((group) => {
    group.querySelectorAll(":scope > .reveal").forEach((el, i) => el.style.setProperty("--i", String(i)));
  });
  const io = new IntersectionObserver(
    (entries, obs) => {
      entries.forEach((entry) => {
        if (entry.isIntersecting) { entry.target.classList.add("in"); obs.unobserve(entry.target); }
      });
    },
    { rootMargin: "0px 0px -10% 0px", threshold: 0.1 }
  );
  els.forEach((el) => io.observe(el));
}
