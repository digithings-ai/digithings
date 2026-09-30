'use client';

import Link from 'next/link';
import { Menu, Search } from 'lucide-react';
import { Button, Sheet, SheetContent, SheetDescription, SheetTitle } from '@digithings/ui/ui';
import { useAppShell } from '@/components/app-shell-context';
import { DashboardMark } from '@/components/dashboard-mark';
import { SidebarBody } from './sidebar';

/** < md: sticky app bar + the sidebar body in a kit Sheet (scroll lock, focus trap, Escape). */
export default function MobileBar() {
  const { mobileNavOpen, setMobileNavOpen, openCommandPalette } = useAppShell();
  const close = () => setMobileNavOpen(false);

  return (
    <>
      <div
        data-print-hide
        className="sticky top-0 z-30 flex h-12 shrink-0 items-center justify-between border-b border-hair bg-surface px-2 md:hidden"
      >
        <Button
          type="button"
          variant="ghost"
          size="icon"
          aria-label="Open navigation"
          aria-expanded={mobileNavOpen}
          aria-controls="app-sidebar-nav"
          onClick={() => setMobileNavOpen(true)}
        >
          <Menu />
        </Button>
        <Link href="/" className="inline-flex items-center gap-2 font-mono text-[0.8rem] text-ink">
          <DashboardMark />
          <span>
            digi<span className="text-accent">quant</span>
          </span>
        </Link>
        <Button type="button" variant="ghost" size="icon" aria-label="Search" onClick={openCommandPalette}>
          <Search />
        </Button>
      </div>
      <Sheet open={mobileNavOpen} onOpenChange={setMobileNavOpen}>
        <SheetContent side="left" showCloseButton={false} className="w-72 max-w-[85vw] bg-surface p-0 sm:max-w-[85vw]">
          <SheetTitle className="sr-only">Navigation</SheetTitle>
          <SheetDescription className="sr-only">Dashboard navigation, status and account</SheetDescription>
          <div id="app-sidebar-nav" className="h-full min-h-0">
            <SidebarBody forceExpanded onNavigate={close} />
          </div>
        </SheetContent>
      </Sheet>
    </>
  );
}
