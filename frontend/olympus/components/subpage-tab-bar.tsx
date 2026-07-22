'use client';

import {
  Children,
  isValidElement,
  useEffect,
  useRef,
  type MouseEvent as ReactMouseEvent,
  type MouseEventHandler,
  type ReactNode,
} from 'react';
import { usePathname } from 'next/navigation';
import { TabStrip } from '@digithings/web';

/** Max width and horizontal padding for portfolio, research, overview, and related pages. */
export const SUBPAGE_MAX = 'max-w-[1600px] mx-auto w-full px-4 md:px-6';

export function subpageTabButtonClass(active: boolean): string {
  return `flex items-center gap-1.5 rounded-lg border px-3 py-1.5 text-xs font-medium transition-colors sm:gap-2 sm:px-4 sm:py-2 sm:text-sm shrink-0 ${
    active
      ? 'bg-accent/15 text-accent border-accent/40'
      : 'text-ink-soft border-transparent hover:bg-ink/[0.04] hover:text-ink'
  }`;
}

/**
 * Mobile grammar: a nowrap, horizontally-scrollable chip row (scrollbar hidden
 * via .subnav-scroll in globals.css). The previous "Sections" hamburger +
 * dropdown stacked a second icon-menu directly under the app-nav hamburger —
 * two adjacent menus on one screen (#1570). A scroll row keeps every section
 * visible and one tap away; the clipped trailing chip is the scroll affordance.
 */
const MOBILE_ROW = 'max-md:flex-nowrap max-md:overflow-x-auto subnav-scroll';

/** Tabs container: desktop wraps in place; mobile is the scroll row. */
export function subpageTabsContainerClass(): string {
  return `flex gap-2 md:flex-row md:flex-wrap ${MOBILE_ROW}`;
}

/**
 * Strip-backed variant: the children serve ONLY the mobile row (the desktop
 * row is the shared <TabStrip/>), so the container hides at >= md instead of
 * becoming the desktop row.
 */
function mobileTabsContainerClass(): string {
  return `flex gap-2 md:hidden ${MOBILE_ROW}`;
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
 * the children map onto it (see mapStripItems); below md the SAME chips render
 * as a horizontally-scrollable row (no menu — #1570) with the active chip
 * kept fully visible using the smallest necessary scroll. Public API is
 * unchanged — consumers keep passing
 * `subpageTabButtonClass`-styled buttons or links.
 */
export function SubpageStickyTabBar({
  children,
  'aria-label': ariaLabel = 'Section navigation',
  topOffset = 'app',
}: {
  children?: ReactNode;
  'aria-label'?: string;
  topOffset?: 'app' | 'none';
}) {
  const topClass = topOffset === 'none' ? 'top-0' : 'max-md:top-[72px] md:top-0';
  const pathname = usePathname();
  const containerRef = useRef<HTMLDivElement>(null);

  const stripItems = mapStripItems(children);
  const activeIndex = stripItems ? stripItems.findIndex((t) => t.active) : -1;

  // Mobile scroll row: keep the active chip in view when the route or the
  // active button-tab changes. block:'nearest' keeps the page's vertical
  // scroll untouched; guarded to the mobile range so the desktop wrap row
  // (or TabStrip) never triggers ancestor scrolling.
  useEffect(() => {
    if (typeof window === 'undefined') return;
    if (!window.matchMedia('(max-width: 767px)').matches) return;
    const active = containerRef.current?.querySelector<HTMLElement>('[class*="border-accent"]');
    active?.scrollIntoView({ inline: 'nearest', block: 'nearest' });
  }, [pathname, activeIndex]);

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
        {stripItems ? (
          <div className="hidden md:block">
            <TabStrip
              tabs={stripItems.map((t, i) => ({ id: String(i), label: t.label }))}
              active={activeIndex}
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
          className={stripItems ? mobileTabsContainerClass() : subpageTabsContainerClass()}
        >
          {children}
        </div>
      </div>
    </div>
  );
}
