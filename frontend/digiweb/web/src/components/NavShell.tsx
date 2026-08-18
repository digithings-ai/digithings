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
 *
 * A `links` entry may be a NavGroup ({ label, items }) instead of a NavLink: on
 * the wide bar it becomes a real dropdown menu (button[aria-haspopup=menu] +
 * div[role=menu] + a[role=menuitem], one open at a time) carrying the
 * menu-button pattern's core keyboard grammar — Enter/Space, ArrowDown/ArrowUp,
 * Home/End, Escape, Tab out, outside press — but not the WAI-ARIA APG's
 * character typeahead; in the narrow sheet — already a vertical list — it
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
import { navMenuIntent } from "./nav-menu-core";

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
  /** Accessible name for the wayfinding <nav> landmark (strip and sheet share
   *  it — only one of the two is ever exposed at a given breakpoint/state).
   *  Default "Primary". Override it when a page mounts more than one bar (the
   *  design reference frames several specimens), so the landmarks stay
   *  distinguishable. */
  navLabel?: string;
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
    } else if (e.key === "Tab" && open) {
      // The pointer path opens the panel and leaves focus right here, so Tab is
      // a real exit from an open menu — and it must take the panel with it, or
      // it hangs over the page with aria-expanded="true" while focus walks on
      // (and Escape, a document listener, could later yank focus back). No
      // preventDefault: the move itself is the browser's to make. Guarded on
      // `open` because onClose() writes the parent's single open-group slot,
      // which a closed group must never touch.
      onClose();
    }
  };

  // Focus leaving the group closes it — one path covering the trigger, the
  // panel, Tab, Shift+Tab and a click that lands on some other control.
  // `relatedTarget` has to be a real element: focus going nowhere (a press on
  // inert page furniture, or on the panel's own padding) is the pointerdown
  // listener's business, which knows whether the press was actually outside.
  const onWrapBlur = (e: ReactFocusEvent<HTMLDivElement>) => {
    if (!open) return;
    const next = e.relatedTarget as Node | null;
    if (next && !wrapRef.current?.contains(next)) onClose();
  };

  const onMenuKeyDown = (e: ReactKeyboardEvent<HTMLDivElement>) => {
    // focusIndex is authoritative: items are tabIndex=-1, so focus only ever
    // enters the panel programmatically — whenever this handler can fire, the
    // focused item is the one focusIndex names.
    const intent = navMenuIntent(e.key, focusIndex ?? 0, group.items.length);
    if (!intent) return;
    if (intent.kind === "focus") {
      e.preventDefault();
      setFocusIndex(intent.index);
    } else if (intent.kind === "activate") {
      // Space on an <a href> does nothing but scroll — and a dropdown locks no
      // scroll (unlike the sheet), so the page would slide under an open menu.
      e.preventDefault();
      itemRefs.current[intent.index]?.click();
    } else {
      // Tab out: park focus on the trigger *before* closing. focus() is
      // synchronous, so the browser's sequential navigation starts from a
      // visible element; left on an item, it would restart from the top of the
      // page once the close turns the panel `visibility: hidden`. No
      // preventDefault — Tab and Shift+Tab both stay the browser's move.
      triggerRef.current?.focus();
      onClose();
    }
    // Escape is handled by the document listener above (one code path for
    // "close and return focus", wherever focus currently sits).
  };

  return (
    <div className="nav-shell-group" ref={wrapRef} data-open={open} onBlur={onWrapBlur}>
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
  label,
  openKey,
  setOpenKey,
}: {
  items: NavItem[];
  className?: string;
  label: string;
  openKey: string | null;
  setOpenKey: (key: string | null) => void;
}) {
  return (
    <nav className={className} aria-label={label}>
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
  label,
  onNavigate,
}: {
  items: NavItem[];
  className?: string;
  label: string;
  onNavigate?: () => void;
}) {
  return (
    <nav className={className} aria-label={label}>
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
  navLabel = "Primary",
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

  // Scroll grammar (canon: settle, then yield). Class flips over React state:
  // scroll fires per frame and the bar's dress is pure presentation.
  useEffect(() => {
    const nav = navRef.current;
    if (!nav) return;
    let last = 0;
    const onScroll = () => {
      const y = window.scrollY;
      nav.classList.toggle("is-scrolled", y > 8);
      // An open dropdown pins the bar (nav-shell.css overrides the transform),
      // so .is-hidden must not accumulate underneath it: closing the group
      // would hand the class back and the bar would slide away under the
      // cursor. Read the attribute React owns instead of taking a dep, so the
      // listener still subscribes exactly once.
      if (y > last && y > 180 && nav.dataset.groupOpen !== "true") nav.classList.add("is-hidden");
      else nav.classList.remove("is-hidden");
      last = y;
    };
    onScroll();
    window.addEventListener("scroll", onScroll, { passive: true });
    return () => window.removeEventListener("scroll", onScroll);
  }, []);

  // The other half of that pin: the bar may already be yielded when a group
  // opens (a keyboard user can reach a trigger on a bar the CSS then brings
  // back). Clear the class as well as override it, so the close is not where
  // the user discovers a stale .is-hidden.
  useEffect(() => {
    if (openGroup === null) return;
    navRef.current?.classList.remove("is-hidden");
  }, [openGroup]);

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
          <NavShellSheetNav
            items={links}
            className="nav-shell-sheet-links"
            label={navLabel}
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
            label={navLabel}
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
