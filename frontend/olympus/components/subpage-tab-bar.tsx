'use client';

import type { ReactNode } from 'react';

/** Max width and horizontal padding for portfolio, research, overview, and related pages. */
export const SUBPAGE_MAX = 'max-w-[1600px] mx-auto w-full px-4 md:px-6';

export function subpageTabButtonClass(active: boolean): string {
  return `flex items-center gap-1.5 rounded-lg border px-3 py-1.5 text-xs font-medium transition-colors sm:gap-2 sm:px-4 sm:py-2 sm:text-sm ${
    active
      ? 'bg-fin-blue/15 text-fin-blue border-fin-blue/40'
      : 'text-text-secondary border-transparent hover:bg-white/[0.04] hover:text-text-primary'
  }`;
}

/**
 * Classes for the tabs container. Desktop layout is the unprefixed base; the
 * mobile dropdown panel is expressed entirely with `max-md:` so it auto-stops
 * at the `md` breakpoint and needs no `md:` reset. `md:flex` keeps tabs visible
 * at >= md regardless of `open`; below md they show only when `open`.
 */
export function subpageTabsContainerClass(open: boolean): string {
  return `gap-2 flex-row flex-wrap md:flex ${open ? 'flex' : 'hidden'} max-md:flex-col max-md:absolute max-md:left-0 max-md:right-0 max-md:top-full max-md:mt-1 max-md:rounded-lg max-md:border max-md:border-border-subtle max-md:bg-bg-glass/95 max-md:backdrop-blur-md max-md:p-2 max-md:shadow-lg max-md:z-30`;
}

/** Sticks under the main scroll so in-page tabs stay visible (Portfolio, Research). */
export function SubpageStickyTabBar({
  children,
  'aria-label': ariaLabel = 'Section navigation',
  topOffset = 'app',
}: {
  children: ReactNode;
  'aria-label'?: string;
  topOffset?: 'app' | 'none';
}) {
  const topClass = topOffset === 'none' ? 'top-0' : 'max-md:top-[72px] md:top-0';
  return (
    <div
      className={`sticky z-20 shrink-0 border-b border-border-subtle bg-bg-glass/95 backdrop-blur-md ${topClass} ${SUBPAGE_MAX} py-3`}
      role="navigation"
      aria-label={ariaLabel}
    >
      <div className="flex flex-wrap gap-2">{children}</div>
    </div>
  );
}
