"use client";
/**
 * Scroll-aware top nav for every digithings.ai page.
 * Wide: brand · inline links · theme + GitHub.
 * Narrow: brand · theme + GitHub + hamburger — links + Ask digichat live in a full-height sheet.
 */
import { useCallback, useEffect, useRef, useState } from "react";
import { createPortal } from "react-dom";
import Link from "next/link";
import { ThemeToggle } from "@digithings/web";
import { Brand, DT_NAV_PRIMARY } from "@/app/_nav";
import { DigiChatMark } from "@/components/DigiChatMark";

function GitHubGlyph() {
  return (
    <svg viewBox="0 0 24 24" width="18" height="18" fill="currentColor" aria-hidden="true">
      <path d="M12 .5C5.7.5.5 5.7.5 12c0 5.1 3.3 9.4 7.9 10.9.6.1.8-.2.8-.6v-2c-3.2.7-3.9-1.5-3.9-1.5-.5-1.3-1.3-1.7-1.3-1.7-1.1-.7.1-.7.1-.7 1.2.1 1.8 1.2 1.8 1.2 1 1.8 2.7 1.3 3.4 1 .1-.8.4-1.3.7-1.6-2.6-.3-5.3-1.3-5.3-5.8 0-1.3.5-2.3 1.2-3.1-.1-.3-.5-1.5.1-3.1 0 0 1-.3 3.3 1.2a11.5 11.5 0 0 1 6 0C17 4.7 18 5 18 5c.6 1.6.2 2.8.1 3.1.8.8 1.2 1.8 1.2 3.1 0 4.5-2.7 5.5-5.3 5.8.4.4.8 1.1.8 2.2v3.3c0 .4.2.7.8.6 4.6-1.5 7.9-5.8 7.9-10.9C23.5 5.7 18.3.5 12 .5z" />
    </svg>
  );
}

function NavLinks({
  className,
  onNavigate,
}: {
  className?: string;
  onNavigate?: () => void;
}) {
  return (
    <nav className={className} aria-label="Primary">
      {DT_NAV_PRIMARY.map((l) => (
        <a
          key={l.href + l.label}
          href={l.href}
          target={l.external ? "_blank" : undefined}
          rel={l.external ? "noopener noreferrer" : undefined}
          onClick={onNavigate}
        >
          {l.label}
          {l.external && <span aria-hidden="true"> ↗</span>}
        </a>
      ))}
    </nav>
  );
}

export function DigiNav() {
  const navRef = useRef<HTMLElement>(null);
  const [menuOpen, setMenuOpen] = useState(false);
  const [portalReady, setPortalReady] = useState(false);

  const closeMenu = useCallback(() => setMenuOpen(false), []);

  useEffect(() => {
    setPortalReady(true);
  }, []);

  useEffect(() => {
    const nav = navRef.current;
    if (!nav) return;
    let last = 0;
    const onScroll = () => {
      const y = window.scrollY;
      nav.classList.toggle("scrolled", y > 8);
      if (y > last && y > 180) nav.classList.add("hidden");
      else nav.classList.remove("hidden");
      last = y;
    };
    onScroll();
    window.addEventListener("scroll", onScroll, { passive: true });
    return () => window.removeEventListener("scroll", onScroll);
  }, []);

  useEffect(() => {
    document.body.style.overflow = menuOpen ? "hidden" : "";
    return () => {
      document.body.style.overflow = "";
    };
  }, [menuOpen]);

  useEffect(() => {
    if (!menuOpen) return;
    const onKey = (e: KeyboardEvent) => {
      if (e.key === "Escape") closeMenu();
    };
    window.addEventListener("keydown", onKey);
    return () => window.removeEventListener("keydown", onKey);
  }, [menuOpen, closeMenu]);

  const menuOverlay =
    portalReady &&
    createPortal(
      <>
        <div
          role="button"
          className={`dqnav-backdrop${menuOpen ? " is-open" : ""}`}
          aria-label="Close menu"
          aria-hidden={!menuOpen}
          tabIndex={menuOpen ? 0 : -1}
          onClick={closeMenu}
          onKeyDown={(e) => {
            if (e.key === "Enter" || e.key === " ") {
              e.preventDefault();
              closeMenu();
            }
          }}
        />
        <div
          id="dqnav-sheet"
          className={`dqnav-sheet${menuOpen ? " is-open" : ""}`}
          aria-hidden={!menuOpen}
        >
          <NavLinks className="dqnav-sheet-links" onNavigate={closeMenu} />
          <div className="dqnav-sheet-cta">
            <Link
              className="btn btn-primary"
              href="/chat"
              onClick={closeMenu}
              aria-label="Ask digichat"
            >
              <DigiChatMark size={18} />
              Ask digichat
            </Link>
          </div>
        </div>
      </>,
      document.body,
    );

  return (
    <>
    <header className={`dqnav${menuOpen ? " menu-open" : ""}`} ref={navRef}>
      <div className="wrap">
        <div className="dqnav-lead">
          <Link className="brand" href="/" aria-label="digithings home" onClick={closeMenu}>
            <Brand />
          </Link>
        </div>
        <NavLinks className="dqnav-links" />
        <div className="dqnav-cta">
          <ThemeToggle />
          <a
            className="btn btn-ghost btn-sm btn-icon"
            href="https://github.com/digithings-ai"
            target="_blank"
            rel="noopener noreferrer"
            aria-label="digithings on GitHub"
          >
            <GitHubGlyph />
          </a>
          <button
            type="button"
            className="dqnav-toggle"
            aria-label={menuOpen ? "Close menu" : "Open menu"}
            aria-expanded={menuOpen}
            aria-controls="dqnav-sheet"
            onClick={() => setMenuOpen((v) => !v)}
          >
            <span aria-hidden="true" />
            <span aria-hidden="true" />
          </button>
        </div>
      </div>
    </header>
    {menuOverlay}
    </>
  );
}
