"use client";

/**
 * Pinned zoom-morph — mined from revolut.com's between-sections transition,
 * where a full-bleed visual scales and rounds down to dock as a card in the
 * next section while that section's copy rises in beside it.
 *
 * Scroll is read the same way as ResearchPipeline: a passive scroll handler
 * measures the wrapper's position and writes transforms straight to refs (no
 * Motion useScroll — which can silently compile a numeric range-map to a
 * view() timeline and break pinned mappings; and no per-frame React state).
 * Reduced motion renders the docked end state as a static, un-pinned block.
 */
import { useEffect, useRef } from "react";

const clamp = (v: number, a: number, b: number) => Math.max(a, Math.min(b, v));

export function SectionMorph() {
  const wrapRef = useRef<HTMLDivElement>(null);
  const panelRef = useRef<HTMLDivElement>(null);
  const heroRef = useRef<HTMLDivElement>(null);
  const copyRef = useRef<HTMLDivElement>(null);

  useEffect(() => {
    const wrap = wrapRef.current;
    const panel = panelRef.current;
    const hero = heroRef.current;
    const copy = copyRef.current;
    if (!wrap || !panel || !hero || !copy) return;

    const apply = (p: number) => {
      const m = clamp((p - 0.1) / 0.55, 0, 1); // morph over the middle of the pin
      panel.style.transform = `scale(${1 - m * 0.52})`;
      panel.style.borderRadius = `${12 + m * 12}px`;
      hero.style.opacity = `${1 - clamp(m * 1.7, 0, 1)}`;
      const c = clamp((p - 0.5) / 0.32, 0, 1); // copy arrives after the morph
      copy.style.opacity = `${c}`;
      copy.style.transform = `translateY(${(1 - c) * 26}px)`;
    };

    if (window.matchMedia("(prefers-reduced-motion: reduce)").matches) {
      apply(1);
      return;
    }

    let ticking = false;
    const onScroll = () => {
      if (ticking) return;
      ticking = true;
      requestAnimationFrame(() => {
        const rect = wrap.getBoundingClientRect();
        const vh = window.innerHeight;
        const p = clamp((vh * 0.12 - rect.top) / (rect.height - vh * 0.85), 0, 1);
        apply(p);
        ticking = false;
      });
    };
    onScroll();
    window.addEventListener("scroll", onScroll, { passive: true });
    window.addEventListener("resize", onScroll, { passive: true });
    return () => {
      window.removeEventListener("scroll", onScroll);
      window.removeEventListener("resize", onScroll);
    };
  }, []);

  return (
    <div className="sm-wrap" ref={wrapRef}>
      <div className="sm-stage">
        <div className="sm-panel" ref={panelRef}>
          <div className="sm-visual" aria-hidden="true" />
          <div className="sm-hero" ref={heroRef}>
            <span className="sm-eyebrow">{"// research"}</span>
            <p className="sm-hero-title">Ask in plain language.</p>
          </div>
        </div>
        <div className="sm-copy" ref={copyRef}>
          <p className="kicker">{"// backtest"}</p>
          <h3 className="sm-copy-title">The same surface, docked as a result.</h3>
          <p className="sm-copy-body">
            Scroll and the hero panel scales and rounds down into a card while the next section&apos;s
            copy rises in beside it — one continuous motion that carries you from one section to the
            next instead of a hard cut.
          </p>
        </div>
      </div>
    </div>
  );
}
