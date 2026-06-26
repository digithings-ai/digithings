"use client";
/**
 * Scroll-aware top nav for every digiquant.io page (ported from v7).
 *   - transparent over the hero at the top of the page
 *   - gains a blurred background + hairline once scrolled
 *   - auto-hides on scroll-down, reappears on scroll-up
 * Class toggles are applied imperatively via a ref so a scroll handler never
 * triggers a React re-render. Reuses the shared `Brand`, `.btn`, and
 * `ThemeToggle` so it stays consistent with the rest of the design system.
 */
import { useEffect, useRef } from "react";
import { ThemeToggle } from "@digithings/web";
import { Brand, DQ_NAV_PRIMARY } from "@/app/_nav";

// Glyphs rendered locally (the shared NavLink type carries no icon field). The
// Olympus mark mirrors the peak path used in PipelineScene's scene header.
function GitHubGlyph() {
  return (
    <svg viewBox="0 0 24 24" width="18" height="18" fill="currentColor" aria-hidden="true">
      <path d="M12 .5C5.7.5.5 5.7.5 12c0 5.1 3.3 9.4 7.9 10.9.6.1.8-.2.8-.6v-2c-3.2.7-3.9-1.5-3.9-1.5-.5-1.3-1.3-1.7-1.3-1.7-1.1-.7.1-.7.1-.7 1.2.1 1.8 1.2 1.8 1.2 1 1.8 2.7 1.3 3.4 1 .1-.8.4-1.3.7-1.6-2.6-.3-5.3-1.3-5.3-5.8 0-1.3.5-2.3 1.2-3.1-.1-.3-.5-1.5.1-3.1 0 0 1-.3 3.3 1.2a11.5 11.5 0 0 1 6 0C17 4.7 18 5 18 5c.6 1.6.2 2.8.1 3.1.8.8 1.2 1.8 1.2 3.1 0 4.5-2.7 5.5-5.3 5.8.4.4.8 1.1.8 2.2v3.3c0 .4.2.7.8.6 4.6-1.5 7.9-5.8 7.9-10.9C23.5 5.7 18.3.5 12 .5z" />
    </svg>
  );
}
function OlympusGlyph() {
  return (
    <svg viewBox="0 0 24 24" width="16" height="16" fill="none" stroke="currentColor" strokeWidth="1.7" strokeLinecap="round" strokeLinejoin="round" aria-hidden="true">
      <path d="M2 19h20M4 19l5-9 4 5 2-3 5 7" />
    </svg>
  );
}

export function DqNav() {
  const navRef = useRef<HTMLElement>(null);

  useEffect(() => {
    const nav = navRef.current;
    if (!nav) return;
    let last = 0;
    const onScroll = () => {
      const y = window.scrollY;
      nav.classList.toggle("scrolled", y > 8);
      // hide once we're past the fold and moving down; reveal on any scroll-up
      if (y > last && y > 180) nav.classList.add("hidden");
      else nav.classList.remove("hidden");
      last = y;
    };
    onScroll();
    window.addEventListener("scroll", onScroll, { passive: true });
    return () => window.removeEventListener("scroll", onScroll);
  }, []);

  return (
    <header className="dqnav" ref={navRef}>
      <div className="wrap">
        <a className="brand" href="/" aria-label="digiquant home">
          <Brand />
        </a>
        <nav className="dqnav-links" aria-label="Primary">
          {DQ_NAV_PRIMARY.map((l) => (
            <a
              key={l.href + l.label}
              href={l.href}
              target={l.external ? "_blank" : undefined}
              rel={l.external ? "noopener noreferrer" : undefined}
            >
              {l.label}
              {l.external && <span aria-hidden="true"> ↗</span>}
            </a>
          ))}
        </nav>
        <div className="dqnav-cta">
          <ThemeToggle />
          <a
            className="btn btn-ghost btn-sm btn-icon"
            href="https://github.com/digithings-ai"
            target="_blank"
            rel="noopener noreferrer"
            aria-label="digiquant on GitHub"
          >
            <GitHubGlyph />
          </a>
          <a className="btn btn-primary btn-sm dqnav-olympus" href="/olympus/">
            <OlympusGlyph />
            <span>Open Olympus</span>
          </a>
        </div>
      </div>
    </header>
  );
}
