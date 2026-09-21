'use client';

import { Menu, Search, X } from 'lucide-react';
import { Button } from '@digithings/ui/ui';
import { DashboardMark } from '@/components/dashboard-mark';
import { useAppShell } from '@/components/app-shell-context';

/**
 * Small-screen top bar: a reserved row so page content is never covered by a
 * floating trigger, and the mobile counterpart of the fixed sidebar rail. The
 * brand row height matches the sidebar header (`min-h-[72px]`) so the two
 * read as one chrome.
 *
 * Rebuilt on the shared grammar: flat surface, small type, kit `Button`s at
 * default dress (no backdrop blur, no hand-rolled borders).
 */
export default function MobileAppBar() {
  const { mobileNavOpen, toggleMobileNav, openCommandPalette } = useAppShell();

  return (
    <header
      data-print-hide
      className="sticky top-0 z-[997] flex shrink-0 border-b border-hair bg-surface pt-[env(safe-area-inset-top,0px)] md:hidden"
      aria-label="digiquant"
    >
      <div className="flex min-h-[72px] w-full items-center justify-between gap-2 px-4 sm:px-6">
        <Button
          type="button"
          variant="ghost"
          size="icon-lg"
          onClick={toggleMobileNav}
          className="shrink-0"
          aria-expanded={mobileNavOpen}
          aria-controls="app-sidebar-nav"
          aria-label={mobileNavOpen ? 'Close navigation menu' : 'Open navigation menu'}
        >
          {mobileNavOpen ? <X size={20} /> : <Menu size={20} />}
        </Button>
        <div className="flex min-w-0 flex-1 items-center justify-center">
          <DashboardMark className="shrink-0" />
        </div>
        <Button
          type="button"
          variant="ghost"
          size="icon-lg"
          onClick={openCommandPalette}
          className="shrink-0"
          aria-label="Search"
        >
          <Search size={18} />
        </Button>
      </div>
    </header>
  );
}
