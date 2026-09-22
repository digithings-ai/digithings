'use client';

import { Menu, Search, X } from 'lucide-react';
import { Button } from '@digithings/ui/ui';
import { DashboardMark } from '@/components/dashboard-mark';
import { useAppShell } from '@/components/app-shell-context';

/**
 * Replaces the floating hamburger: reserved top row so content is not covered on small screens.
 * Brand row height matches the sidebar header (`min-h-[72px]`) for visual consistency.
 */
export default function MobileAppBar() {
  const { mobileNavOpen, toggleMobileNav, openCommandPalette } = useAppShell();

  return (
    <header
      data-print-hide
      className="sticky top-0 z-[997] flex shrink-0 border-b border-hair bg-surface/95 pt-[env(safe-area-inset-top,0px)] backdrop-blur-md md:hidden"
      aria-label="digiquant"
    >
      <div className="flex min-h-[72px] w-full items-center justify-between gap-2 px-4 sm:px-6">
        <Button
          type="button"
          variant="ghost"
          size="icon-lg"
          onClick={toggleMobileNav}
          className="shrink-0 rounded-none border border-hair text-ink hover:bg-ink/[0.06]"
          aria-expanded={mobileNavOpen}
          aria-controls="app-sidebar-nav"
          aria-label={mobileNavOpen ? 'Close navigation menu' : 'Open navigation menu'}
        >
          {mobileNavOpen ? <X size={22} strokeWidth={2} /> : <Menu size={22} strokeWidth={2} />}
        </Button>
        <div className="flex min-w-0 flex-1 items-center justify-center">
          <DashboardMark className="shrink-0" />
        </div>
        <Button
          type="button"
          variant="ghost"
          size="icon-lg"
          onClick={openCommandPalette}
          className="shrink-0 rounded-none border border-hair text-ink hover:bg-ink/[0.06]"
          aria-label="Search"
        >
          <Search size={20} strokeWidth={2} />
        </Button>
      </div>
    </header>
  );
}
