"use client";

/**
 * Stacking panels — the second between-sections transition mined from
 * revolut.com. Each panel pins in turn and the next slides up over it (rounded
 * top + shadow give the layered seam); as a panel is covered it scales back and
 * dims. The "covered" amount keys off the *next* panel's approach to the pin
 * line — not the panel's own view progress — so it's driven by a manual
 * scroll handler writing to refs (same pattern as ResearchPipeline / the
 * zoom-morph), which also keeps it verifiable. Reduced motion: a plain stack.
 */
import { useEffect, useRef } from "react";

const clamp = (v: number, a: number, b: number) => Math.max(a, Math.min(b, v));

const PANELS = [
  { n: "01", title: "Ingest", body: "Free macro and market data, pulled and normalized into one store." },
  { n: "02", title: "Backtest", body: "Replay on a NautilusTrader core — full trade ledger, one tearsheet." },
  { n: "03", title: "Execute", body: "Promote up the ladder to live — every rung of it a human gate." },
];

export function StackingPanels() {
  const panelRefs = useRef<(HTMLElement | null)[]>([]);

  useEffect(() => {
    const panels = panelRefs.current.filter(Boolean) as HTMLElement[];
    if (panels.length < 2) return;
    if (window.matchMedia("(prefers-reduced-motion: reduce)").matches) return;

    const stickyTop = parseFloat(getComputedStyle(panels[0]).top) || 70;

    let ticking = false;
    const onScroll = () => {
      if (ticking) return;
      ticking = true;
      requestAnimationFrame(() => {
        const coverStart = window.innerHeight * 0.55;
        for (let i = 0; i < panels.length - 1; i++) {
          const nextTop = panels[i + 1].getBoundingClientRect().top;
          const covered = clamp((stickyTop + coverStart - nextTop) / coverStart, 0, 1);
          panels[i].style.transform = `translateY(${covered * -14}px) scale(${1 - covered * 0.06})`;
          const dim = panels[i].querySelector<HTMLElement>(".stk-dim");
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
  }, []);

  return (
    <div className="stk-wrap">
      {PANELS.map((p, i) => (
        <section
          key={p.n}
          className="stk-panel"
          ref={(el) => {
            panelRefs.current[i] = el;
          }}
        >
          <div className="stk-inner">
            <span className="stk-n">{p.n}</span>
            <h3 className="stk-title">{p.title}</h3>
            <p className="stk-body">{p.body}</p>
          </div>
          <span className="stk-dim" aria-hidden="true" />
        </section>
      ))}
    </div>
  );
}
