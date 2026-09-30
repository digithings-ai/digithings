'use client';

import type { ReactNode } from 'react';
import { usePathname } from 'next/navigation';
import { useEffect } from 'react';
import { SidebarInset, SidebarProvider, TooltipProvider } from '@digithings/ui/ui';
import { useAppShell } from '@/components/app-shell-context';
import CommandPalette from '@/components/command-palette';
import DigichatPopup from '@/components/digichat-popup';
import FxHubOnlyGuard from '@/components/fx-hub-only-guard';
import DbUnavailable from '@/components/db-unavailable';
import { SUBPAGE_MAX } from '@/components/layout-constants';
import { useDashboard } from '@/lib/dashboard-context';
import { isDbExempt } from '@/lib/nav';
import MobileBar from './mobile-bar';
import { PageHeader, PageHeaderProvider, usePageLayout } from './page-header';
import DashboardSidebar from './sidebar';

const MAIN_BY_LAYOUT = {
  contained: `${SUBPAGE_MAX} py-4 md:py-6 group-data-[density=comfortable]/shell:py-8`,
  fluid: 'w-full px-4 md:px-6 py-4 md:py-6',
  canvas: 'w-full overflow-hidden',
} as const;

/** '/' opens the palette unless the visitor is typing or a dialog owns the keyboard. */
function useSlashPalette(open: () => void) {
  useEffect(() => {
    const onKey = (e: KeyboardEvent) => {
      if (e.key !== '/' || e.metaKey || e.ctrlKey || e.altKey) return;
      const t = e.target as HTMLElement | null;
      if (t && (t.isContentEditable || /^(INPUT|TEXTAREA|SELECT)$/.test(t.tagName) || t.closest('[role="dialog"]'))) return;
      e.preventDefault();
      open();
    };
    window.addEventListener('keydown', onKey);
    return () => window.removeEventListener('keydown', onKey);
  }, [open]);
}

function ShellFrame({ children }: { children: ReactNode }) {
  const pathname = usePathname();
  const { dbStatus } = useDashboard();
  const shell = useAppShell();
  const layout = usePageLayout();
  const gated = dbStatus !== 'ok' && !isDbExempt(pathname);
  useSlashPalette(shell.openCommandPalette);

  return (
    <SidebarProvider
      open={!shell.sidebarCollapsed}
      onOpenChange={(open) => shell.setSidebarCollapsed(!open)}
      width={shell.sidebarWidth}
      onWidthChange={shell.setSidebarWidth}
      data-density={shell.density}
      suppressHydrationWarning
      className="group/shell bg-bg font-mono text-ink"
    >
      <DashboardSidebar />
      <SidebarInset>
        <MobileBar />
        <PageHeader />
        <main
          id="main"
          className={`flex min-h-0 min-w-0 flex-1 flex-col ${layout === 'canvas' ? 'overflow-hidden' : 'overflow-y-auto'}`}
        >
          <div className={`flex min-h-0 flex-1 flex-col ${MAIN_BY_LAYOUT[layout]}`}>
            {gated ? <DbUnavailable /> : <FxHubOnlyGuard>{children}</FxHubOnlyGuard>}
          </div>
        </main>
      </SidebarInset>
      <CommandPalette />
      {/* Desk+ research/portfolio digichat popup (#3422); no-ops when env off. */}
      <DigichatPopup />
    </SidebarProvider>
  );
}

/**
 * The dashboard shell: persistent left sidebar (rail-collapsible; a Sheet drawer
 * below md), a page-header band, and exactly one `<main>` that owns scrolling.
 * The sidebar is a flex sibling, so it can never cover content. The DB-down gate
 * swaps only the page for the standard card; the shell stays mounted and
 * DB-exempt routes (lib/nav.ts) stay live. AppShellProvider is mounted by AuthGate.
 */
export default function AppShell({ children }: { children: ReactNode }) {
  return (
    <TooltipProvider delay={200}>
      <PageHeaderProvider>
        <ShellFrame>{children}</ShellFrame>
      </PageHeaderProvider>
    </TooltipProvider>
  );
}
