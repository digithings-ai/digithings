"use client";
/**
 * NavShell — the one scroll-aware top bar for every DigiThings marketing surface.
 * Wide: brand · inline links · theme toggle + tail actions.
 * Narrow: brand · theme + actions + hamburger — links and the app CTA live in a
 * full-height portal sheet. Supersedes the per-app DqNav / DigiNav copies:
 * everything app-specific arrives as props (brand, links, sheet CTA, tail
 * actions such as a GitHub icon link); everything shared is owned here —
 * settle after 8px (hairline + blurred band), yield past 180px on scroll-down
 * and return on scroll-up, body scroll lock, Escape/scrim dismissal, and the
 * SSR-safe mount gate for the portal. State dress + overlay machinery live in
 * ../styles/nav-shell.css; static layout is token-backed utilities.
 */
import {
  useCallback,
  useEffect,
  useId,
  useRef,
  useState,
  useSyncExternalStore,
  type ReactNode,
} from "react";
import { createPortal } from "react-dom";
import { ThemeToggle } from "./ThemeProvider";
import type { NavLink } from "./chrome";

// Mount gate: server + first (hydration) client render read `false`; the client
// re-reads `true` post-hydration. Keeps the portal out of the SSR/hydration tree
// so it can't cause a mismatch — without a setState-in-effect cascade.
const emptySubscribe = () => () => {};

export interface NavShellProps {
  /** Brand content (mark + wordmark); NavShell wraps it in the home link. */
  brand: ReactNode;
  /** Wayfinding links — inline on wide viewports, stacked in the sheet on narrow. */
  links: NavLink[];
  /** App CTA for the narrow-viewport sheet (e.g. Olympus / Ask digichat button). */
  cta?: ReactNode;
  /** Extra tail actions between the theme toggle and the hamburger
   *  (e.g. a `.btn-icon` GitHub link) — kept a slot so the primitive carries
   *  no hardcoded external URLs. */
  actions?: ReactNode;
  /** Render the shared ThemeToggle in the tail cluster. Default true. */
  showThemeToggle?: boolean;
  /** Home link target for the brand. Default "/". */
  homeHref?: string;
  /** Accessible label for the brand home link (e.g. "digiquant home"). */
  homeLabel?: string;
}

function NavShellLinks({
  links,
  className,
  onNavigate,
}: {
  links: NavLink[];
  className?: string;
  onNavigate?: () => void;
}) {
  return (
    <nav className={className} aria-label="Primary">
      {links.map((l) => (
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

export function NavShell({
  brand,
  links,
  cta,
  actions,
  showThemeToggle = true,
  homeHref = "/",
  homeLabel = "home",
}: NavShellProps) {
  const navRef = useRef<HTMLElement>(null);
  const [menuOpen, setMenuOpen] = useState(false);
  const sheetId = useId();
  const mounted = useSyncExternalStore(
    emptySubscribe,
    () => true,
    () => false,
  );

  const closeMenu = useCallback(() => setMenuOpen(false), []);

  // Scroll grammar (canon: settle, then yield). Class flips over React state:
  // scroll fires per frame and the bar's dress is pure presentation.
  useEffect(() => {
    const nav = navRef.current;
    if (!nav) return;
    let last = 0;
    const onScroll = () => {
      const y = window.scrollY;
      nav.classList.toggle("is-scrolled", y > 8);
      if (y > last && y > 180) nav.classList.add("is-hidden");
      else nav.classList.remove("is-hidden");
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
    mounted &&
    createPortal(
      <>
        <div
          role="button"
          className={`nav-shell-backdrop${menuOpen ? " is-open" : ""}`}
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
          id={sheetId}
          className={`nav-shell-sheet${menuOpen ? " is-open" : ""}`}
          aria-hidden={!menuOpen}
        >
          <NavShellLinks links={links} className="nav-shell-sheet-links" onNavigate={closeMenu} />
          {cta && <div className="nav-shell-sheet-cta">{cta}</div>}
        </div>
      </>,
      document.body,
    );

  return (
    <>
      <header ref={navRef} className={`nav-shell${menuOpen ? " is-menu-open" : ""}`}>
        <div className="nav-shell-row relative z-[56] mx-auto flex w-full max-w-[var(--wrap,1180px)] items-center justify-between gap-[1.5rem] px-[var(--gutter,1.5rem)] max-[880px]:gap-[1rem]">
          <div className="nav-shell-lead flex min-w-0 items-center">
            <a
              className="nav-shell-brand inline-flex items-center gap-[0.6rem] font-semibold lowercase tracking-[-0.02em] text-ink"
              href={homeHref}
              aria-label={homeLabel}
              onClick={closeMenu}
            >
              {brand}
            </a>
          </div>
          <NavShellLinks
            links={links}
            className="nav-shell-links flex gap-[1.8rem] text-[0.9rem] text-ink-soft max-[880px]:hidden"
          />
          <div className="nav-shell-tail flex items-center gap-[0.9rem] max-[560px]:shrink-0 max-[560px]:gap-[0.5rem]">
            {showThemeToggle && <ThemeToggle />}
            {actions}
            <button
              type="button"
              className="nav-shell-toggle"
              aria-label={menuOpen ? "Close menu" : "Open menu"}
              aria-expanded={menuOpen}
              aria-controls={sheetId}
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
