"use client";

import Link from "next/link";
import { usePathname } from "next/navigation";
import { useEffect, useState } from "react";
import { ThemeToggle } from "@digithings/web";

const PAGES = [
  { href: "/", label: "Foundations" },
  { href: "/typography", label: "Typography" },
  { href: "/data", label: "Data" },
  { href: "/effects", label: "Effects" },
  { href: "/chrome", label: "Chrome" },
  { href: "/terminal", label: "Terminal" },
  { href: "/symbols", label: "Symbols" },
  { href: "/account", label: "Account" },
] as const;

/** Shared top bar for the design-reference app. Each page holds one family
 *  of design elements; the bar is the only chrome shared across them.
 *  Below 901px the links collapse behind a hamburger that opens a full-width
 *  sheet with dialog semantics (Escape closes, backdrop closes, rows stay
 *  ≥44px touch targets) — the pattern mined from graphite's mobile nav. */
export function SiteNav() {
  const pathname = usePathname();
  const [open, setOpen] = useState(false);
  const [lastPathname, setLastPathname] = useState(pathname);

  // Close the sheet on route change (covers back/forward navigation) via the
  // adjust-state-during-render pattern — no setState-in-effect cascade.
  if (lastPathname !== pathname) {
    setLastPathname(pathname);
    if (open) setOpen(false);
  }

  useEffect(() => {
    if (!open) return;
    const onKey = (e: KeyboardEvent) => {
      if (e.key === "Escape") setOpen(false);
    };
    document.addEventListener("keydown", onKey);
    return () => document.removeEventListener("keydown", onKey);
  }, [open]);

  const isActive = (href: string) => (href === "/" ? pathname === "/" : pathname.startsWith(href));

  return (
    <nav className="site-nav" aria-label="Design reference sections">
      <Link href="/" className="site-nav-mark">
        design<em>ref</em>
      </Link>

      <ul className="site-nav-links">
        {PAGES.map((page) => (
          <li key={page.href}>
            <Link href={page.href} aria-current={isActive(page.href) ? "page" : undefined}>
              {page.label}
            </Link>
          </li>
        ))}
      </ul>

      <ThemeToggle className="site-nav-theme" />

      <button
        type="button"
        className="site-nav-burger"
        aria-expanded={open}
        aria-controls="site-nav-sheet"
        aria-label={open ? "Close navigation" : "Open navigation"}
        onClick={() => setOpen((v) => !v)}
      >
        <svg viewBox="0 0 16 16" width="16" height="16" aria-hidden="true">
          {open ? (
            <path d="M3 3l10 10M13 3L3 13" stroke="currentColor" strokeWidth="1.5" />
          ) : (
            <path d="M1 4h14M1 8h14M1 12h14" stroke="currentColor" strokeWidth="1.5" />
          )}
        </svg>
      </button>

      {open ? (
        <>
          <div className="site-nav-scrim" onClick={() => setOpen(false)} aria-hidden="true" />
          <div id="site-nav-sheet" className="site-nav-sheet" role="dialog" aria-label="Navigation">
            <ul>
              {PAGES.map((page) => (
                <li key={page.href}>
                  <Link
                    href={page.href}
                    aria-current={isActive(page.href) ? "page" : undefined}
                    onClick={() => setOpen(false)}
                  >
                    {page.label}
                  </Link>
                </li>
              ))}
            </ul>
          </div>
        </>
      ) : null}
    </nav>
  );
}
