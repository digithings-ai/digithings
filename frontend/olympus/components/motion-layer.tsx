"use client";
/**
 * MotionLayer — non-invasive "comes to life" scroll reveals for the dashboard.
 * Adds `html.motion-on` only when motion is allowed (JS active + not reduced),
 * then reveals `.glass-card` and `[data-reveal]` elements. With JS off or
 * reduced-motion, nothing is hidden (content always shown). Pure CSS +
 * IntersectionObserver — no animation library, no edits to data components,
 * CSP-safe.
 *
 * `motion-on` hides un-revealed cards (opacity:0), so the reveal MUST be
 * bullet-proof or content silently disappears. This effect runs once and the
 * layout never remounts, so client-side navigation and tab switches mount fresh
 * cards into a live DOM. Two rules keep those visible:
 *   1. Cards already in the viewport at scan time are revealed immediately
 *      instead of waiting on the observer — an above-the-fold card mounted by a
 *      tab switch would otherwise never receive an intersection callback and
 *      stay invisible until a hard refresh.
 *   2. The MutationObserver lives for the page's lifetime (rAF-debounced) so
 *      panels that mount after navigation are always re-scanned. It previously
 *      self-disconnected after 8s, which left anything mounted later hidden.
 */
import { useEffect } from "react";

export default function MotionLayer() {
  useEffect(() => {
    const root = document.documentElement;
    if (matchMedia("(prefers-reduced-motion: reduce)").matches || !("IntersectionObserver" in window)) return;
    root.classList.add("motion-on");

    const seen = new WeakSet<Element>();
    const io = new IntersectionObserver(
      (entries) => {
        for (const e of entries) {
          if (e.isIntersecting) {
            e.target.classList.add("reveal-in");
            io.unobserve(e.target);
          }
        }
      },
      { rootMargin: "0px 0px -8% 0px", threshold: 0.08 }
    );

    const inViewport = (el: HTMLElement) => {
      const r = el.getBoundingClientRect();
      return r.bottom > 0 && r.top < (window.innerHeight || document.documentElement.clientHeight);
    };

    const observe = () => {
      document.querySelectorAll<HTMLElement>(".glass-card, [data-reveal]").forEach((el) => {
        if (seen.has(el)) return;
        seen.add(el);
        // Reveal anything already on-screen now (initial load, or a card mounted
        // above the fold by client-side nav / a tab switch); only defer to the
        // observer for cards genuinely below the fold.
        if (inViewport(el)) {
          el.classList.add("reveal-in");
        } else {
          io.observe(el);
        }
      });
    };
    observe();

    // Re-scan as client-rendered data panels mount — for the page's lifetime,
    // debounced to one scan per frame so a busy dashboard stays cheap.
    let raf = 0;
    const schedule = () => {
      if (raf) return;
      raf = requestAnimationFrame(() => {
        raf = 0;
        observe();
      });
    };
    const mo = new MutationObserver(schedule);
    mo.observe(document.body, { childList: true, subtree: true });

    return () => {
      io.disconnect();
      mo.disconnect();
      if (raf) cancelAnimationFrame(raf);
      root.classList.remove("motion-on");
    };
  }, []);

  return null;
}
