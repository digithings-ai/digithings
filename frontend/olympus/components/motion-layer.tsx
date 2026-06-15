"use client";
/**
 * MotionLayer — non-invasive "comes to life" scroll reveals for the dashboard.
 * Adds `html.motion-on` only when motion is allowed (JS active + not reduced),
 * then reveals `.glass-card` and `[data-reveal]` elements as they scroll into
 * view. With JS off or reduced-motion, nothing is hidden (content always shown).
 * Pure CSS + IntersectionObserver — no animation library, no edits to the
 * data components, CSP-safe.
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

    const observe = () => {
      document.querySelectorAll<HTMLElement>(".glass-card, [data-reveal]").forEach((el) => {
        if (seen.has(el)) return;
        seen.add(el);
        // already-visible-on-load elements reveal immediately (no flash of empty)
        io.observe(el);
      });
    };
    observe();
    // re-scan as client-rendered data panels mount
    const mo = new MutationObserver(observe);
    mo.observe(document.body, { childList: true, subtree: true });
    const stop = setTimeout(() => mo.disconnect(), 8000);

    return () => { io.disconnect(); mo.disconnect(); clearTimeout(stop); root.classList.remove("motion-on"); };
  }, []);

  return null;
}
