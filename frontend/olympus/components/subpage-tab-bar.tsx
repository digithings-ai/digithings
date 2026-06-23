'use client';

import { useEffect, useState, type ReactNode } from 'react';
import { usePathname } from 'next/navigation';
import { Menu, X } from 'lucide-react';

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

  // Close the mobile menu on route change (covers <Link> tabs).
  useEffect(() => {
    // eslint-disable-next-line react-hooks/set-state-in-effect -- close menu on navigation
    setOpen(false);
  }, [pathname]);

  // Close on Escape while the menu is open.
  useEffect(() => {
    if (!open) return;
    const onKey = (e: KeyboardEvent) => {
      if (e.key === 'Escape') setOpen(false);
    };
    window.addEventListener('keydown', onKey);
    return () => window.removeEventListener('keydown', onKey);
  }, [open]);

  return (
    <div
      className={`sticky z-20 shrink-0 border-b border-border-subtle bg-bg-glass/95 backdrop-blur-md ${topClass}`}
      role="navigation"
      aria-label={ariaLabel}
    >
      <div className={`${SUBPAGE_MAX} relative py-3`}>
        <button
          type="button"
          onClick={() => setOpen((o) => !o)}
          className="relative z-30 flex items-center gap-2 rounded-lg border border-border-subtle px-3 py-1.5 text-sm font-medium text-text-primary hover:bg-white/[0.06] md:hidden"
          aria-expanded={open}
          aria-controls="subpage-tabs"
          aria-label={open ? 'Close sections menu' : 'Open sections menu'}
        >
          {open ? <X size={18} strokeWidth={2} /> : <Menu size={18} strokeWidth={2} />}
          <span>{menuLabel}</span>
        </button>
        {open ? (
          <div
            className="fixed inset-0 z-[19] md:hidden"
            onClick={() => setOpen(false)}
            aria-hidden
          />
        ) : null}
        <div id="subpage-tabs" className={subpageTabsContainerClass(open)} onClick={() => setOpen(false)}>
          {children}
        </div>
      </div>
    </div>
  );
}
