"use client";

import { useEffect, useRef, type ReactNode } from "react";

/**
 * StackingPanels — the layered between-sections transition promoted from the
 * design reference (effects/stacking-panels; mined from revolut.com). Each
 * panel pins in turn and the next slides up over it (rounded top + shadow
 * give the layered seam); as a panel is covered it scales back and dims.
 *
 * The "covered" amount keys off the *next* panel's approach to the pin line —
 * not the panel's own view progress — so it's driven by a manual scroll
 * handler writing to refs (the ResearchPipeline / zoom-morph pattern), which
 * also keeps it verifiable. Scroll mechanics stay here per migrate-vs-leave;
 * only the panel CONTENT arrives via props. Reduced motion: a plain sticky
 * stack, no transform/dim writes. Content is server-rendered and fully
 * readable with no JS.
 *
 * The sticky pin offset reads `--nav-h` from the consuming app (fallback
 * 3.4rem) — see styles/effects-chrome.css.
 *
 * Wiring (in the consuming app):
 *   globals.css   @import "@digithings/web/styles/effects-chrome.css";
 *                 @source "<path-to>/digiweb/web/src/components/effects-chrome";
 */
export type StackingPanel = {
  /** Mono accent index over the title — "01", "2.0" … */
  tag: string;
  /** Serif panel title. */
  title: string;
  /** One or two sentences of mechanism. */
  body: ReactNode;
};

export type StackingPanelsProps = {
  panels: StackingPanel[];
  className?: string;
};

const clamp = (v: number, a: number, b: number) => Math.max(a, Math.min(b, v));

export function StackingPanels({ panels, className }: StackingPanelsProps) {
  const panelRefs = useRef<(HTMLElement | null)[]>([]);

  useEffect(() => {
    const els = panelRefs.current.filter(Boolean) as HTMLElement[];
    if (els.length < 2) return;
    if (window.matchMedia("(prefers-reduced-motion: reduce)").matches) return;

    const stickyTop = parseFloat(getComputedStyle(els[0]).top) || 70;

    let ticking = false;
    const onScroll = () => {
      if (ticking) return;
      ticking = true;
      requestAnimationFrame(() => {
        const coverStart = window.innerHeight * 0.55;
        for (let i = 0; i < els.length - 1; i++) {
          const nextTop = els[i + 1].getBoundingClientRect().top;
          const covered = clamp((stickyTop + coverStart - nextTop) / coverStart, 0, 1);
          els[i].style.transform = `translateY(${covered * -14}px) scale(${1 - covered * 0.06})`;
          const dim = els[i].querySelector<HTMLElement>(".stk-dim");
          if (dim) dim.style.opacity = `${covered * 0.55}`;
        }
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
  }, [panels.length]);

  return (
    <div className={className}>
      {panels.map((p, i) => (
        <section
          key={p.tag}
          className="stk-panel"
          ref={(el) => {
            panelRefs.current[i] = el;
          }}
        >
          <div className="relative z-[1] max-w-[34rem]">
            <span className="font-mono text-[0.7rem] tracking-[0.14em] text-accent">{p.tag}</span>
            <h3 className="mt-[0.4rem] font-display font-normal text-[clamp(1.8rem,4vw,2.8rem)] tracking-[-0.015em] text-ink">
              {p.title}
            </h3>
            <p className="mt-[0.7rem] max-w-[42ch] text-[0.95rem] leading-[1.6] text-ink-soft">
              {p.body}
            </p>
          </div>
          <span className="stk-dim" aria-hidden="true" />
        </section>
      ))}
    </div>
  );
}
