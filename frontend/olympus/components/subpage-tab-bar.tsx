'use client';

import { createPortal } from 'react-dom';
import {
  Children,
  isValidElement,
  useEffect,
  useRef,
  useState,
  type MouseEvent as ReactMouseEvent,
  type MouseEventHandler,
  type ReactNode,
} from 'react';
import { usePathname } from 'next/navigation';
import { Menu, X } from 'lucide-react';
import { TabStrip } from '@digithings/web';

/** Max width and horizontal padding for portfolio, research, overview, and related pages. */
export const SUBPAGE_MAX = 'max-w-[1600px] mx-auto w-full px-4 md:px-6';

export function subpageTabButtonClass(active: boolean): string {
  return `flex items-center gap-1.5 rounded-lg border px-3 py-1.5 text-xs font-medium transition-colors sm:gap-2 sm:px-4 sm:py-2 sm:text-sm ${
    active
      ? 'bg-accent/15 text-accent border-accent/40'
      : 'text-ink-soft border-transparent hover:bg-ink/[0.04] hover:text-ink'
  }`;
}

/** Dropdown-panel chrome, gated behind max-md so none of it leaks to desktop. */
const TAB_PANEL_CHROME =
  'max-md:flex-col max-md:absolute max-md:left-0 max-md:right-0 max-md:top-full max-md:mt-1 max-md:rounded-lg max-md:border max-md:border-hair max-md:bg-surface/95 max-md:p-2 max-md:shadow-lg max-md:z-30';

/**
 * Classes for the tabs container. Desktop layout uses `md:flex-row md:flex-wrap`
 * so direction and wrapping live on the same min-width range as `md:flex`,
 * eliminating any generation-order reliance against `max-md:flex-col` and
 * keeping the mobile dropdown a clean (non-wrapping) column. `md:flex` keeps
 * tabs visible at >= md regardless of `open`; below md they show only when
 * `open`. The panel's backdrop-blur is intentionally omitted here — the
 * outer sticky bar already applies `backdrop-blur-md` to that region; a second
 * layer would produce an additive double-blur artifact.
 */
export function subpageTabsContainerClass(open: boolean): string {
  return `gap-2 md:flex-row md:flex-wrap md:flex ${open ? 'flex' : 'hidden'} ${TAB_PANEL_CHROME}`;
}

/**
 * Strip-backed variant: the children serve ONLY the mobile dropdown (the
 * desktop row is the shared <TabStrip/>), so the container hides at >= md
 * instead of becoming the desktop row.
 */
function mobileTabsContainerClass(open: boolean): string {
  return `gap-2 md:hidden ${open ? 'flex' : 'hidden'} ${TAB_PANEL_CHROME}`;
}

type TabButtonProps = {
  className?: string;
  onClick?: MouseEventHandler<HTMLButtonElement>;
  children?: ReactNode;
};

type StripItem = {
  label: ReactNode;
  active: boolean;
  onClick?: MouseEventHandler<HTMLButtonElement>;
};

/**
 * Map the tab children onto <TabStrip/> items — possible only when every
 * child follows the documented contract: a plain <button> styled with
 * `subpageTabButtonClass`, exactly one of them active. Anything else (most
 * notably <Link> tabs, e.g. Portfolio's section nav) returns null and keeps
 * the plain desktop row: route navigation is nav-link semantics (cmd-click,
 * prefetch, aria-current), not an ARIA tablist — backing links with
 * role="tab" buttons would regress both.
 */
function mapStripItems(children: ReactNode): StripItem[] | null {
  const items: StripItem[] = [];
  for (const kid of Children.toArray(children)) {
    if (!isValidElement<TabButtonProps>(kid) || kid.type !== 'button') return null;
    const cls = kid.props.className;
    const active = cls === subpageTabButtonClass(true);
    if (!active && cls !== subpageTabButtonClass(false)) return null;
    items.push({ label: kid.props.children, active, onClick: kid.props.onClick });
  }
  if (items.length === 0 || items.filter((t) => t.active).length !== 1) return null;
  return items;
}

/**
 * Sticks under the main scroll so in-page tabs stay visible (Portfolio,
 * Research). The desktop row is backed by the shared <TabStrip/> (chip
 * dress — sliding accent indicator, roving tabindex, aria-selected) whenever
 * the children map onto it (see mapStripItems); the sticky offset, mobile
 * dropdown, and portal scrim stay olympus-local. Public API is unchanged —
 * consumers keep passing `subpageTabButtonClass`-styled buttons or links.
 */
export function SubpageStickyTabBar({
  children,
  'aria-label': ariaLabel = 'Section navigation',
  topOffset = 'app',
  menuLabel = 'Sections',
}: {
  children?: ReactNode;
  'aria-label'?: string;
  topOffset?: 'app' | 'none';
  menuLabel?: string;
}) {
  const topClass = topOffset === 'none' ? 'top-0' : 'max-md:top-[72px] md:top-0';
  const [open, setOpen] = useState(false);
  const pathname = usePathname();
  const triggerRef = useRef<HTMLButtonElement>(null);
  const containerRef = useRef<HTMLDivElement>(null);

  const stripItems = mapStripItems(children);

  // Close the mobile menu on route change (covers <Link> tabs).
  useEffect(() => {
    // eslint-disable-next-line react-hooks/set-state-in-effect -- close menu on navigation
    setOpen(false);
  }, [pathname]);

  // Close on Escape while the menu is open; restore focus to trigger on close.
  useEffect(() => {
    if (!open) return;
    // Move focus to the first focusable item in the panel on open.
    containerRef.current?.querySelector<HTMLElement>('button, a')?.focus();
    const onKey = (e: KeyboardEvent) => {
      if (e.key === 'Escape') {
        setOpen(false);
        triggerRef.current?.focus();
      }
    };
    window.addEventListener('keydown', onKey);
    return () => window.removeEventListener('keydown', onKey);
  }, [open]);

  // TabStrip owns the desktop buttons, so re-dispatch activation to the
  // consumer's own handler. Call sites use `() => setTab(id)`-style handlers;
  // the stub keeps a defensive preventDefault/stopPropagation surface for
  // any future handler that touches the event.
  const activateStripTab = (i: number) => {
    const stub = {
      preventDefault() {},
      stopPropagation() {},
    } as unknown as ReactMouseEvent<HTMLButtonElement>;
    stripItems?.[i]?.onClick?.(stub);
  };

  return (
    <div
      className={`sticky z-20 shrink-0 border-b border-hair bg-surface/95 backdrop-blur-md ${topClass}`}
      role="navigation"
      aria-label={ariaLabel}
    >
      <div className={`${SUBPAGE_MAX} relative py-3`}>
        <button
          ref={triggerRef}
          type="button"
          onClick={() => setOpen((o) => !o)}
          className="relative z-30 flex items-center gap-2 rounded-lg border border-hair px-3 py-1.5 text-sm font-medium text-ink hover:bg-ink/[0.06] md:hidden"
          aria-expanded={open}
          aria-controls="subpage-tabs"
          aria-label={`${open ? 'Close' : 'Open'} ${menuLabel} menu`}
        >
          {open ? <X size={18} strokeWidth={2} /> : <Menu size={18} strokeWidth={2} />}
          <span>{menuLabel}</span>
        </button>
        {open
          ? createPortal(
              <div
                className="fixed inset-0 z-[19] md:hidden"
                onClick={() => setOpen(false)}
                tabIndex={-1}
                aria-hidden
              />,
              document.body,
            )
          : null}
        {stripItems ? (
          <div className="hidden md:block">
            <TabStrip
              tabs={stripItems.map((t, i) => ({ id: String(i), label: t.label }))}
              active={stripItems.findIndex((t) => t.active)}
              onChange={activateStripTab}
              label={ariaLabel}
              variant="chip"
              linkPanels={false}
            />
          </div>
        ) : null}
        <div
          ref={containerRef}
          id="subpage-tabs"
          className={stripItems ? mobileTabsContainerClass(open) : subpageTabsContainerClass(open)}
          onClick={(e) => {
            if ((e.target as HTMLElement).closest('button, a')) setOpen(false);
          }}
        >
          {children}
        </div>
      </div>
    </div>
  );
}
