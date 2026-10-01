'use client';

import Link from 'next/link';
import { Menu, Search } from 'lucide-react';
import { Button, useSidebar } from '@digithings/ui/ui';
import { useAppShell } from '@/components/app-shell-context';
import { DashboardMark } from '@/components/dashboard-mark';

/** < md: sticky app bar; the kit Sidebar opens as a Sheet from the hamburger. */
export default function MobileBar() {
  const { openMobile, setOpenMobile } = useSidebar();
  const { openCommandPalette } = useAppShell();

  return (
    <div
      data-print-hide
      className="sticky top-0 z-30 flex h-12 shrink-0 items-center justify-between border-b border-hair bg-surface px-2 md:hidden"
    >
      <Button
        type="button"
        variant="ghost"
        size="icon"
        aria-label="Open navigation"
        aria-expanded={openMobile}
        aria-controls="app-sidebar-nav"
        onClick={() => setOpenMobile(true)}
      >
        <Menu />
      </Button>
      <Link href="/" className="inline-flex items-center gap-2.5 font-mono text-[0.75rem] text-ink">
        <DashboardMark size={16} />
        <span>
          digi<span className="text-accent">quant</span>
        </span>
      </Link>
      <Button type="button" variant="ghost" size="icon" aria-label="Search" onClick={openCommandPalette}>
        <Search />
      </Button>
    </div>
  );
}
