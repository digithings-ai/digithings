"use client";

/**
 * Cross-fade + parallax reveal — the softest of the three between-sections
 * transitions mined from revolut.com. Each block's distance from the viewport
 * centre drives its opacity (adjacent blocks dissolve into one another) and a
 * per-child parallax offset (children rise in at staggered rates). Driven by a
 * manual rAF scroll handler that writes opacity + a single `--e` custom
 * property per block; children read `--e` with their own `--d` multiplier in
 * CSS. Reduced motion: every block at rest, fully visible.
 */
import { useEffect, useRef } from "react";

const clamp = (v: number, a: number, b: number) => Math.max(a, Math.min(b, v));

const BLOCKS = [
  { k: "// signal", t: "It starts with a question.", b: "Ask in plain language; a research loop turns it into something testable." },
  { k: "// proof", t: "The market answers.", b: "Eight years of bars, replayed deterministically — the edge is real or it isn't." },
  { k: "// ship", t: "Then it goes live.", b: "Promoted rung by rung, each one gated by a human who owns the call." },
];

export function CrossfadeSections() {
  const blockRefs = useRef<(HTMLElement | null)[]>([]);

  useEffect(() => {
    const blocks = blockRefs.current.filter(Boolean) as HTMLElement[];
    if (!blocks.length) return;
    if (window.matchMedia("(prefers-reduced-motion: reduce)").matches) return;

    let ticking = false;
    const onScroll = () => {
      if (ticking) return;
      ticking = true;
      requestAnimationFrame(() => {
        const vh = window.innerHeight;
        blocks.forEach((el) => {
          const rect = el.getBoundingClientRect();
          const nd = (rect.top + rect.height / 2 - vh / 2) / (vh * 0.72);
          el.style.opacity = String(clamp(1 - Math.abs(nd), 0, 1));
          el.style.setProperty("--e", String(clamp(nd, -1.3, 1.3)));
        });
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

  // The wrapper margin and the kicker/title/body type migrate to token-backed
  // Tailwind utilities via the @theme bridge. .cf-block stays as CSS: the JS
  // writes its opacity + --e live, the .cf-block > * combinator drives the
  // per-child parallax, and the reduced-motion !important resets both — all
  // genuine mechanics that must not become utilities.
  return (
    <div className="mt-[1.6rem]">
      {BLOCKS.map((b, i) => (
        <section
          key={b.k}
          className="cf-block"
          ref={(el) => {
            blockRefs.current[i] = el;
          }}
        >
          <p
            className="m-0 font-mono text-[0.7rem] tracking-[0.14em] uppercase text-accent"
            style={{ "--d": 1 } as React.CSSProperties}
          >
            {b.k}
          </p>
          <h3
            className="mt-[0.5rem] font-display font-normal text-[clamp(2rem,5vw,3.4rem)] tracking-[-0.02em] leading-[1.05] text-ink"
            style={{ "--d": 1.7 } as React.CSSProperties}
          >
            {b.t}
          </h3>
          <p
            className="mt-[0.9rem] max-w-[44ch] text-[1rem] leading-[1.6] text-ink-soft"
            style={{ "--d": 2.6 } as React.CSSProperties}
          >
            {b.b}
          </p>
        </section>
      ))}
    </div>
  );
}
