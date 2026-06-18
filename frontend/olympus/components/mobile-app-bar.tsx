'use client';

import { Menu, X } from 'lucide-react';
import { AtlasMark } from '@/components/atlas-mark';
import { useAppShell } from '@/components/app-shell-context';

/**
 * Replaces the floating hamburger: reserved top row so content is not covered on small screens.
 * Brand row height matches the sidebar header (`min-h-[72px]`) for visual consistency.
 */
export default function MobileAppBar() {
  const { mobileNavOpen, toggleMobileNav } = useAppShell();

  return (
    <header
      className="sticky top-0 z-[997] flex shrink-0 border-b border-border-subtle bg-bg-glass/95 pt-[env(safe-area-inset-top,0px)] backdrop-blur-md md:hidden"
      aria-label="Atlas"
    >
      <div className="flex min-h-[72px] w-full items-center justify-between gap-2 px-4 sm:px-6">
        <button
          type="button"
          onClick={toggleMobileNav}
          className="flex h-9 w-9 shrink-0 items-center justify-center rounded-lg border border-border-subtle text-text-primary hover:bg-white/[0.06]"
          aria-expanded={mobileNavOpen}
          aria-controls="app-sidebar-nav"
          aria-label={mobileNavOpen ? 'Close navigation menu' : 'Open navigation menu'}
        >
          {mobileNavOpen ? <X size={22} strokeWidth={2} /> : <Menu size={22} strokeWidth={2} />}
        </button>
        <div className="flex min-w-0 flex-1 items-center justify-center">
          <AtlasMark className="shrink-0" />
        </div>
        <div className="h-9 w-9 shrink-0" aria-hidden />
      </div>
    </header>
  );
}
