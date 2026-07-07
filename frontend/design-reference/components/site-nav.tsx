"use client";

import Link from "next/link";
import { usePathname } from "next/navigation";
import { useEffect, useState, useSyncExternalStore } from "react";
import { createPortal } from "react-dom";
import { ThemeToggle } from "@digithings/web";
import {
  applyLivery,
  getLiverySnapshot,
  getLiveryServerSnapshot,
  LIVERY_OPTIONS,
  subscribeLivery,
} from "@/components/livery-store";

const PAGES = [
  { href: "/", label: "Foundations" },
  { href: "/controls", label: "Controls" },
  { href: "/layout-patterns", label: "Layout" },
  { href: "/typography", label: "Typography" },
  { href: "/data", label: "Data" },
  { href: "/finance", label: "Finance" },
  { href: "/effects", label: "Effects" },
  { href: "/chrome", label: "Chrome" },
  { href: "/terminal", label: "Terminal" },
  { href: "/chatbot", label: "Chatbot" },
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

  const livery = useSyncExternalStore(subscribeLivery, getLiverySnapshot, getLiveryServerSnapshot);

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

      <label className="site-nav-livery">
        <span className="sr-only">Page livery</span>
        <select value={livery} onChange={(e) => applyLivery(e.target.value)}>
          {LIVERY_OPTIONS.map((o) => (
            <option key={o.id} value={o.id}>
              {o.label}
            </option>
          ))}
        </select>
      </label>

      <ThemeToggle className="site-nav-theme" />

      <button
        type="button"
        className={`site-nav-burger${open ? " is-open" : ""}`}
        aria-expanded={open}
        aria-controls="site-nav-sheet"
        aria-label={open ? "Close navigation" : "Open navigation"}
        onClick={() => setOpen((v) => !v)}
      >
        <span aria-hidden="true" />
        <span aria-hidden="true" />
      </button>

      {/* Portaled to body: the nav bar's own backdrop-filter would otherwise
          become the containing block for these fixed overlays. */}
      {open
        ? createPortal(
            <>
              <div className="site-nav-scrim" onClick={() => setOpen(false)} aria-hidden="true" />
              <div
                id="site-nav-sheet"
                className="site-nav-sheet"
                role="dialog"
                aria-label="Navigation"
              >
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
            </>,
            document.body,
          )
        : null}
    </nav>
  );
}
