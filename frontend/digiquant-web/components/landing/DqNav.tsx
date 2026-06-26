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
import { Brand, DQ_NAV_PRIMARY, DQ_NAV_ACTIONS } from "@/app/_nav";

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
          {DQ_NAV_ACTIONS.map((l) => (
            <a
              key={l.href + l.label}
              className={l.cta ? "btn btn-primary btn-sm" : "btn btn-ghost btn-sm"}
              href={l.href}
              target={l.external ? "_blank" : undefined}
              rel={l.external ? "noopener noreferrer" : undefined}
            >
              {l.label}
              {l.external && <span aria-hidden="true"> ↗</span>}
            </a>
          ))}
        </div>
      </div>
    </header>
  );
}
