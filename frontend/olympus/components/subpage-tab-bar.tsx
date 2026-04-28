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

/** Sticks under the main scroll so in-page tabs stay visible (Portfolio, Research). */
export function SubpageStickyTabBar({
  children,
  'aria-label': ariaLabel = 'Section navigation',
}: {
  children: ReactNode;
  'aria-label'?: string;
}) {
  return (
    <div
      className={`sticky z-20 shrink-0 border-b border-border-subtle bg-bg-glass/95 backdrop-blur-md max-md:top-12 md:top-0 ${SUBPAGE_MAX} py-3`}
      role="navigation"
      aria-label={ariaLabel}
    >
      <div className="flex flex-wrap gap-2">{children}</div>
    </div>
  );
}
