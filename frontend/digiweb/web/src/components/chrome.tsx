"use client";
/** Shared nav, footer, and module card. Brand + links are passed in so both
 *  marketing apps reuse the same chrome. */
import { useRef, useState, type ReactNode } from "react";
import { m, useReducedMotion, useScroll, useTransform } from "motion/react";
import { ThemeToggle } from "./ThemeProvider";
import { Emblem } from "./emblems";
import { StackRow } from "./StackLogo";
import { type ModuleNode } from "../data/modules";

export interface NavLink { label: string; href: string; external?: boolean; cta?: boolean; }

export function Nav({ brand, links, mark }: { brand: ReactNode; links: NavLink[]; mark?: ReactNode }) {
  const [open, setOpen] = useState(false);
  return (
    <header className="site-nav">
      <div className="wrap nav-inner">
        <a className="brand" href="/" aria-label="home">{mark}{brand}</a>
        <nav className={`nav-links${open ? " open" : ""}`} aria-label="Primary">
          {links.map((l) => (
            <a key={l.href + l.label} href={l.href} className={l.cta ? "btn btn-sm" : undefined}
              target={l.external ? "_blank" : undefined} rel={l.external ? "noopener noreferrer" : undefined}
              onClick={() => setOpen(false)}>
              {l.label}{l.external && <span className="ext" aria-hidden="true"> ↗</span>}
            </a>
          ))}
        </nav>
        <div className="nav-tail">
          <ThemeToggle />
          <button className="nav-toggle" aria-label="Toggle navigation" aria-expanded={open}
            onClick={() => setOpen((v) => !v)}><span /><span /></button>
        </div>
      </div>
    </header>
  );
}

export function Footer({ links, meta }: { links: NavLink[]; meta: string }) {
  return (
    <footer className="footer">
      <div className="wrap footer-inner">
        <nav className="footer-links" aria-label="Footer">
          {links.map((l) => (
            <a key={l.href + l.label} href={l.href} target={l.external ? "_blank" : undefined}
              rel={l.external ? "noopener noreferrer" : undefined}>{l.label}</a>
          ))}
        </nav>
        <p className="footer-meta">{meta}</p>
      </div>
    </footer>
  );
}

/** The page's last word (canon §08): the module's name at giant scale,
 *  1px hairline outline by default — plus an opt-in scroll-scrubbed glow
 *  sweep. The outline rise/fill is scroll-scrubbed with zero JS via CSS
 *  `animation-timeline: view()` (@supports-gated in site.css); under
 *  reduced motion or without support the name simply stands. The suffix
 *  wears var(--accent), so each app's livery (or the umbrella's ink)
 *  dresses it automatically. aria-hidden: punctuation, not content.
 *
 *  `sweep` (default false — the outline-only ruling stands for every
 *  existing consumer) adds the reference footer's personality moment: an
 *  accent glow passing left→right across the wordmark, scrubbed by the
 *  colophon's own scroll progress (same offsets/transform as
 *  reference/components/footer-reference.tsx). A duplicate overlay span
 *  carries the gradient clipped to its glyphs; reduced motion (and no-JS)
 *  park the band off-screen so no glow travels. Requires a MotionProvider
 *  in the consuming app. */
export function Colophon({
  name,
  suffix,
  sweep = false,
}: {
  name: string;
  suffix?: string;
  sweep?: boolean;
}) {
  const ref = useRef<HTMLDivElement | null>(null);
  const reduced = useReducedMotion();
  // 0 = the colophon's top enters the viewport bottom; 1 = scrolled to its
  // end. The band travels off-left → off-right across the middle of that
  // range, so the highlight crosses the wordmark once as you scroll into it.
  const { scrollYProgress } = useScroll({
    target: ref,
    offset: ["start end", "end end"],
  });
  const sweepPos = useTransform(scrollYProgress, [0.38, 0.96], [120, -20]);
  const backgroundPosition = useTransform(sweepPos, (v) => `${v}% 0`);

  return (
    <div className="colophon" aria-hidden="true" ref={ref}>
      <span className="colo-word">
        {name}
        {suffix ? <b>{suffix}</b> : null}
        {sweep ? (
          <m.span
            className="colo-sweep"
            style={reduced ? undefined : { backgroundPosition }}
          >
            {name}
            {suffix}
          </m.span>
        ) : null}
      </span>
    </div>
  );
}

export function ModuleCard({ m }: { m: ModuleNode }) {
  return (
    <a className={`mod-card t-${m.tier}`} href={`/modules/${m.id}`}>
      <div className="mod-card-top">
        <Emblem id={m.emblem} size={26} />
        <span className={`dg-tier t-${m.tier}`}>{m.tier}</span>
      </div>
      <h3>{m.name}</h3>
      <p className="role">{m.role}</p>
      <StackRow items={m.stack.slice(0, 4)} className="stack-row compact" />
    </a>
  );
}
