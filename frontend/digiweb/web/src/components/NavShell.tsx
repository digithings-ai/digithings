"use client";
/**
 * NavShell — the one scroll-aware top bar for every digithings marketing surface.
 * Wide: brand · inline links · theme toggle + tail actions.
 * Narrow: brand · theme + actions + hamburger — links and the app CTA live in a
 * full-height portal sheet. Supersedes the per-app DqNav / DigiNav copies:
 * everything app-specific arrives as props (brand, links, sheet CTA, tail
 * actions such as a GitHub icon link); everything shared is owned here —
 * settle after 8px (hairline + blurred band), yield past 180px on scroll-down
 * and return on scroll-up, body scroll lock, Escape/scrim dismissal, and the
 * SSR-safe mount gate for the portal. State dress + overlay machinery live in
 * ../styles/nav-shell.css; static layout is token-backed utilities.
 *
 * A `links` entry may be a NavGroup ({ label, items }) instead of a NavLink: on
 * the wide bar it becomes a real dropdown menu (button[aria-haspopup=menu] +
 * div[role=menu] + a[role=menuitem], WAI-ARIA menu-button keyboard grammar,
 * one open at a time); in the narrow sheet — already a vertical list — it
 * becomes a labelled section of links, no disclosure at all.
 */
import {
  useCallback,
  useEffect,
  useId,
  useRef,
  useState,
  useSyncExternalStore,
  type FocusEvent as ReactFocusEvent,
  type KeyboardEvent as ReactKeyboardEvent,
  type ReactNode,
} from "react";
import { createPortal } from "react-dom";
import { ThemeToggle } from "./ThemeProvider";
import { isNavGroup, type NavGroup, type NavItem, type NavLink } from "./chrome";
import { useBodyScrollLock } from "../lib/useBodyScrollLock";

// Mount gate: server + first (hydration) client render read `false`; the client
// re-reads `true` post-hydration. Keeps the portal out of the SSR/hydration tree
// so it can't cause a mismatch — without a setState-in-effect cascade.
const emptySubscribe = () => () => {};

export interface NavShellProps {
  /** Brand content (mark + wordmark); NavShell wraps it in the home link. */
  brand: ReactNode;
  /** Wayfinding entries — inline on wide viewports, stacked in the sheet on
   *  narrow. A NavGroup entry renders as a dropdown on the bar and as a
   *  labelled section in the sheet. `NavLink[]` is still accepted as-is. */
  links: NavItem[];
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
  /**
   * Show/hide grammar for the bar. Default "scroll" — settle after 8px,
   * yield past 180px on scroll-down, return on scroll-up (the canon
   * behavior, everywhere). "hover" is for a surface that doesn't scroll at
   * all (a fixed-height app view, not a document) — the bar starts hidden
   * and reveals only while the cursor sits in the top strip, so content can
   * run all the way to the top the rest of the time. Keyboard/focus reach
   * is unaffected either way: a hidden bar is still tab-reachable and
   * `:focus-within` reveals it (nav-shell.css).
   */
  autoHide?: "scroll" | "hover";
}

/** Key for a NavItem: groups have no href, so the label carries the identity. */
const itemKey = (item: NavItem, i: number) =>
  isNavGroup(item) ? `g:${i}:${item.label}` : `${item.href}${item.label}`;

/** A plain wayfinding link, in the strip or in the sheet. Menu items are their
 *  own markup inside NavShellGroup — they carry roles, refs and a tabIndex. */
function NavShellLink({ link, onNavigate }: { link: NavLink; onNavigate?: () => void }) {
  return (
    <a
      href={link.href}
      target={link.external ? "_blank" : undefined}
      rel={link.external ? "noopener noreferrer" : undefined}
      onClick={onNavigate}
    >
      {link.label}
      {link.external && <span aria-hidden="true"> ↗</span>}
    </a>
  );
}

/**
 * One dropdown on the wide bar. Own component, not an inline branch, because
 * each group needs its own useId + item refs (hooks can't run in a loop) — and
 * because the open/closed decision belongs to the parent (one at a time) while
 * the focus bookkeeping belongs here.
 */
function NavShellGroup({
  group,
  groupKey,
  open,
  setOpenKey,
}: {
  group: NavGroup;
  /** This group's identity in the parent's single "which one is open" slot. */
  groupKey: string;
  open: boolean;
  /** The parent's useState setter — stable, so the dismissal listeners below
   *  subscribe once per open instead of once per parent render. */
  setOpenKey: (key: string | null) => void;
}) {
  const onOpen = useCallback(() => setOpenKey(groupKey), [setOpenKey, groupKey]);
  const onClose = useCallback(() => setOpenKey(null), [setOpenKey]);
  const menuId = useId();
  const wrapRef = useRef<HTMLDivElement>(null);
  const triggerRef = useRef<HTMLButtonElement>(null);
  const itemRefs = useRef<(HTMLAnchorElement | null)[]>([]);
  // Which item to focus once the panel is *visible*. null = leave focus on the
  // trigger (pointer opens). Applied from an effect, never from the handler:
  // the panel is still visibility:hidden while the handler runs, and a hidden
  // element cannot take focus — the call would silently no-op.
  const [focusIndex, setFocusIndex] = useState<number | null>(null);
  const last = group.items.length - 1;

  useEffect(() => {
    if (!open || focusIndex === null) return;
    const el = itemRefs.current[focusIndex];
    if (!el) return;
    el.focus();
    if (document.activeElement === el) return;
    // The panel unparks through a transition. If the browser has not recomputed
    // its visibility by the time this effect runs, the element is still
    // `visibility: hidden` and focus() is a silent no-op — so retry once on the
    // next frame. (nav-shell.css flips visibility with no delay when opening
    // precisely so the first call lands; this is the belt for anyone who
    // restyles the panel.)
    const raf = requestAnimationFrame(() => el.focus());
    return () => cancelAnimationFrame(raf);
  }, [open, focusIndex]);

  const closeToTrigger = useCallback(() => {
    onClose();
    triggerRef.current?.focus();
  }, [onClose]);

  // Dismissal while open: a pointer press anywhere outside this group, or
  // Escape from anywhere (focus may still be on the trigger, or have been
  // clicked away entirely — a React onKeyDown on the wrapper would miss it).
  useEffect(() => {
    if (!open) return;
    const onPointerDown = (e: PointerEvent) => {
      if (!wrapRef.current?.contains(e.target as Node)) onClose();
    };
    const onKeyDown = (e: globalThis.KeyboardEvent) => {
      if (e.key !== "Escape") return;
      e.preventDefault();
      onClose();
      triggerRef.current?.focus();
    };
    document.addEventListener("pointerdown", onPointerDown);
    document.addEventListener("keydown", onKeyDown);
    return () => {
      document.removeEventListener("pointerdown", onPointerDown);
      document.removeEventListener("keydown", onKeyDown);
    };
  }, [open, onClose]);

  // Enter/Space/ArrowDown/ArrowUp on the trigger: preventDefault stops the
  // browser synthesising a click from Enter/Space, so onClick below stays the
  // pointer path (which must NOT pull focus into the panel).
  const onTriggerKeyDown = (e: ReactKeyboardEvent<HTMLButtonElement>) => {
    if (e.key === "Enter" || e.key === " " || e.key === "ArrowDown") {
      e.preventDefault();
      if (open && e.key !== "ArrowDown") closeToTrigger();
      else {
        onOpen();
        setFocusIndex(0);
      }
    } else if (e.key === "ArrowUp") {
      e.preventDefault();
      onOpen();
      setFocusIndex(last);
    }
  };

  const onMenuKeyDown = (e: ReactKeyboardEvent<HTMLDivElement>) => {
    const current = focusIndex ?? 0;
    if (e.key === "ArrowDown") {
      e.preventDefault();
      setFocusIndex(current >= last ? 0 : current + 1);
    } else if (e.key === "ArrowUp") {
      e.preventDefault();
      setFocusIndex(current <= 0 ? last : current - 1);
    } else if (e.key === "Home") {
      e.preventDefault();
      setFocusIndex(0);
    } else if (e.key === " ") {
      // A menuitem activates on Space as well as Enter — but this one is an <a>,
      // where the browser's default for Space is to scroll the page, and no
      // click is synthesised. So synthesise it and swallow the scroll. Read the
      // focused element rather than focusIndex: focus is the source of truth
      // here, and the index is still null after a pointer open.
      const item = (e.target as HTMLElement).closest<HTMLAnchorElement>("a.nav-shell-menu-item");
      if (item) {
        e.preventDefault();
        item.click();
      }
    } else if (e.key === "End") {
      e.preventDefault();
      setFocusIndex(last);
    }
    // Escape is handled by the document listener above (one code path for
    // "close and return focus", wherever focus currently sits). Tab is handled
    // by onFocusLeave below, not here — closing on keydown would re-hide the
    // panel *before* the browser picks the next tab stop.
  };

  // Tab out of the group — from the trigger or from an item — closes it. Doing
  // this on focusout rather than on the Tab keydown means focus has already
  // landed before the panel re-hides, and it catches every other way focus can
  // leave (a click that focuses something else, a screen reader's own
  // navigation). React's onBlur is focusout, so it bubbles from the children.
  // A null relatedTarget (the window itself lost focus) also closes: returning
  // to the tab with a menu still hanging open is the worse of the two.
  const onFocusLeave = (e: ReactFocusEvent<HTMLDivElement>) => {
    if (!open) return;
    if (wrapRef.current?.contains(e.relatedTarget as Node | null)) return;
    onClose();
  };

  // Hover open/close, alongside the existing click toggle (kept for touch,
  // which never fires hover, and for keyboard, which already opens via
  // onTriggerKeyDown). A short close delay survives the gap between trigger
  // and panel — .nav-shell-menu sits `margin-top` below the trigger, so a
  // straight-line mouse path from one to the other briefly leaves the
  // wrapper's box and would otherwise close it before the panel is reached.
  const closeTimer = useRef<ReturnType<typeof setTimeout> | null>(null);
  const cancelClose = useCallback(() => {
    if (closeTimer.current == null) return;
    clearTimeout(closeTimer.current);
    closeTimer.current = null;
  }, []);
  const onMouseEnter = useCallback(() => {
    cancelClose();
    onOpen();
  }, [cancelClose, onOpen]);
  const onMouseLeave = useCallback(() => {
    cancelClose();
    closeTimer.current = setTimeout(onClose, 150);
  }, [cancelClose, onClose]);
  useEffect(() => cancelClose, [cancelClose]);

  return (
    <div
      className="nav-shell-group"
      ref={wrapRef}
      data-open={open}
      onBlur={onFocusLeave}
      onMouseEnter={onMouseEnter}
      onMouseLeave={onMouseLeave}
    >
      <button
        type="button"
        ref={triggerRef}
        className="nav-shell-group-trigger"
        aria-haspopup="menu"
        aria-expanded={open}
        aria-controls={menuId}
        onClick={() => {
          if (open) onClose();
          else {
            onOpen();
            setFocusIndex(null);
          }
        }}
        onKeyDown={onTriggerKeyDown}
      >
        {group.label}
        <span className="nav-shell-group-caret" aria-hidden="true" />
      </button>
      {/* Always in the tree (so it can transition, and so SSR ships the index),
          hidden by visibility + aria-hidden while closed — the same contract
          the portal sheet below uses. */}
      <div
        id={menuId}
        role="menu"
        aria-label={group.label}
        aria-hidden={!open}
        className={`nav-shell-menu${open ? " is-open" : ""}`}
        onKeyDown={onMenuKeyDown}
      >
        {group.items.map((item, i) => (
          <a
            key={item.href + item.label}
            ref={(el) => {
              itemRefs.current[i] = el;
            }}
            href={item.href}
            className="nav-shell-menu-item"
            role="menuitem"
            // Roving focus: the trigger is the menu's single tab stop and items
            // are focused programmatically — which also keeps the closed
            // panel's links out of the tab order, no inert dance needed.
            tabIndex={-1}
            target={item.external ? "_blank" : undefined}
            rel={item.external ? "noopener noreferrer" : undefined}
            onClick={onClose}
          >
            {item.label}
            {item.external && <span aria-hidden="true"> ↗</span>}
          </a>
        ))}
      </div>
    </div>
  );
}

/** The wide-viewport strip: links inline, groups as dropdowns. */
function NavShellStrip({
  items,
  className,
  openKey,
  setOpenKey,
}: {
  items: NavItem[];
  className?: string;
  openKey: string | null;
  setOpenKey: (key: string | null) => void;
}) {
  return (
    <nav className={className} aria-label="Primary">
      {items.map((item, i) => {
        const key = itemKey(item, i);
        return isNavGroup(item) ? (
          <NavShellGroup
            key={key}
            group={item}
            groupKey={key}
            open={openKey === key}
            setOpenKey={setOpenKey}
          />
        ) : (
          <NavShellLink key={key} link={item} />
        );
      })}
    </nav>
  );
}

/** A group inside the sheet: a label and its links, no disclosure — the sheet
 *  is already a vertical list, so a dropdown inside it would be a second
 *  needless tap. Own component for the useId behind aria-labelledby. */
function NavShellSheetSection({
  group,
  onNavigate,
}: {
  group: NavGroup;
  onNavigate?: () => void;
}) {
  const labelId = useId();
  return (
    <div className="nav-shell-sheet-group" role="group" aria-labelledby={labelId}>
      <p className="nav-shell-sheet-group-label" id={labelId}>
        {group.label}
      </p>
      {group.items.map((item) => (
        <NavShellLink key={item.href + item.label} link={item} onNavigate={onNavigate} />
      ))}
    </div>
  );
}

/** The narrow-viewport sheet's link stack: flat links plus labelled sections. */
function NavShellSheetNav({
  items,
  className,
  onNavigate,
}: {
  items: NavItem[];
  className?: string;
  onNavigate?: () => void;
}) {
  return (
    <nav className={className} aria-label="Primary">
      {items.map((item, i) =>
        isNavGroup(item) ? (
          <NavShellSheetSection key={itemKey(item, i)} group={item} onNavigate={onNavigate} />
        ) : (
          <NavShellLink key={itemKey(item, i)} link={item} onNavigate={onNavigate} />
        ),
      )}
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
  autoHide = "scroll",
}: NavShellProps) {
  const navRef = useRef<HTMLElement>(null);
  const [menuOpen, setMenuOpen] = useState(false);
  // Which dropdown is open, by itemKey — one slot, so opening a second group
  // closes the first without any cross-group bookkeeping.
  const [openGroup, setOpenGroup] = useState<string | null>(null);
  const sheetId = useId();
  const mounted = useSyncExternalStore(
    emptySubscribe,
    () => true,
    () => false,
  );

  const closeMenu = useCallback(() => setMenuOpen(false), []);

  // Scroll grammar (canon: settle, then yield). Class flips outside React
  // state: scroll fires per frame and the bar's dress is pure presentation.
  // Only for autoHide="scroll" — a surface using "hover" below typically
  // doesn't scroll at all (window.scrollY would just stay pinned at 0), and
  // even if it did, the two grammars shouldn't fight over the same class.
  useEffect(() => {
    const nav = navRef.current;
    if (!nav || autoHide !== "scroll") return;
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
  }, [autoHide]);

  // Hover grammar: starts hidden, reveals while the cursor sits in the top
  // strip. RELEASE_ZONE is deliberately wider than the bar itself (a flat
  // HOT_ZONE-only release would flicker right at the reveal boundary, since
  // the reveal transition itself moves the cursor's target out from under
  // it). Focus reach for keyboard users is handled in CSS
  // (.nav-shell.is-hidden:focus-within), not here — a transformed-offscreen
  // element is still in tab order, so no JS is needed for that path.
  //
  // REVEAL_DELAY requires the cursor to *dwell* in HOT_ZONE for a beat
  // before revealing, rather than firing the instant it crosses the line.
  // A "hover" surface has no reserved top padding by design (it overlays on
  // reveal instead of pushing content down), so a consumer's own top-of-
  // viewport content can end up only a few px below HOT_ZONE — e.g.
  // digithings-web's /chat, /chat/occ, whose iframed header (incl. the
  // language selector) sits ~12-28px down. Without a delay, simply moving
  // the cursor *toward* that control — not toward the bar at all — grazes
  // HOT_ZONE en route and reveals the bar over the very control the user
  // was reaching for. A fast pass-through clears the zone before the timer
  // fires; only a genuine paused hover at
  // the top edge reveals it. Mirrors the existing close-delay debounce
  // pattern below (150ms) rather than inventing a new timing idiom.
  //
  // is-scrolled rides along with the reveal (not just is-hidden): in scroll
  // mode that class is what gives the bar its blurred backdrop once there's
  // page content to read it over, gated on actually having scrolled past
  // it. A hover-revealed bar overlays content unconditionally — there's no
  // "haven't scrolled yet" moment where see-through is correct — so it
  // needs that same backdrop every time it's shown, not on a scroll gate
  // that a non-scrolling surface would never trip.
  useEffect(() => {
    const nav = navRef.current;
    if (!nav || autoHide !== "hover") return;
    const HOT_ZONE = 24;
    const RELEASE_ZONE = nav.getBoundingClientRect().height + 64;
    const REVEAL_DELAY = 120;
    nav.classList.add("is-hidden");
    let revealed = false;
    let revealTimer: ReturnType<typeof setTimeout> | null = null;
    const clearRevealTimer = () => {
      if (revealTimer == null) return;
      clearTimeout(revealTimer);
      revealTimer = null;
    };
    const onMove = (e: MouseEvent) => {
      if (!revealed && e.clientY <= HOT_ZONE) {
        if (revealTimer == null) {
          revealTimer = setTimeout(() => {
            revealTimer = null;
            revealed = true;
            nav.classList.remove("is-hidden");
            nav.classList.add("is-scrolled");
          }, REVEAL_DELAY);
        }
      } else if (!revealed) {
        clearRevealTimer();
      } else if (e.clientY > RELEASE_ZONE) {
        revealed = false;
        nav.classList.add("is-hidden");
        nav.classList.remove("is-scrolled");
      }
    };
    // A pending reveal timer only gets cancelled by a later mousemove landing
    // outside HOT_ZONE — but a fast flick off the *top* edge (toward browser
    // chrome, another display, alt-tab) leaves the viewport entirely, so no
    // further mousemove ever fires there to cancel it. Without this, the bar
    // still reveals 120ms later even though the cursor is no longer anywhere
    // near it, defeating the dwell delay via the one path it doesn't cover.
    // documentElement (not window) is what actually receives "left the
    // viewport": mouseleave doesn't bubble, and it's the html element's
    // geometry — filling the viewport — that the pointer exits.
    const onLeaveViewport = () => {
      if (!revealed) clearRevealTimer();
    };
    window.addEventListener("mousemove", onMove, { passive: true });
    document.documentElement.addEventListener("mouseleave", onLeaveViewport);
    return () => {
      window.removeEventListener("mousemove", onMove);
      document.documentElement.removeEventListener("mouseleave", onLeaveViewport);
      clearRevealTimer();
    };
  }, [autoHide]);

  // Reference-counted (see useBodyScrollLock) so this coordinates safely
  // with any other overlay locked at the same time (e.g. CommandPalette),
  // regardless of open/close order — a plain per-component overflow toggle
  // here previously clobbered any other overlay's lock the moment either
  // one closed (confirmed in the in-session review on PR #2269).
  useBodyScrollLock(menuOpen);

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
          <NavShellSheetNav
            items={links}
            className="nav-shell-sheet-links"
            onNavigate={closeMenu}
          />
          {cta && <div className="nav-shell-sheet-cta">{cta}</div>}
        </div>
      </>,
      document.body,
    );

  return (
    <>
      {/* data-* rather than a class: the scroll listener owns .is-scrolled /
          .is-hidden on this same element via classList, and a React className
          rewrite would wipe them. An attribute React alone controls can't
          collide — and it lets CSS pin the bar in place while a menu is open. */}
      <header
        ref={navRef}
        className={`nav-shell${menuOpen ? " is-menu-open" : ""}`}
        data-group-open={openGroup !== null}
      >
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
          <NavShellStrip
            items={links}
            className="nav-shell-links flex gap-[1.8rem] text-[0.9rem] text-ink-soft max-[880px]:hidden"
            openKey={openGroup}
            setOpenKey={setOpenGroup}
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
              onClick={() => {
                // Never leave a dropdown open behind the sheet (possible after
                // a resize across the 880px breakpoint).
                setOpenGroup(null);
                setMenuOpen((v) => !v);
              }}
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
