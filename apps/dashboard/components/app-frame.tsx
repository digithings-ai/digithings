'use client';

import { ReactNode, Suspense } from 'react';
import { usePathname } from 'next/navigation';
import Sidebar from '@/components/sidebar';
import MobileAppBar from '@/components/mobile-app-bar';
import CommandPalette from '@/components/command-palette';
import DigichatPopup from '@/components/digichat-popup';
import FxHubOnlyGuard from '@/components/fx-hub-only-guard';
import DbUnavailable from '@/components/db-unavailable';
import { useAppShell } from '@/components/app-shell-context';
import { mainOffsetClass } from '@/components/layout-constants';
import { useDashboard } from '@/lib/dashboard-context';
import { isDbExempt } from '@/lib/nav';

/**
 * App frame: the dashboard shell (sidebar + page chrome) for all routes.
 *
 * Layout contract (plan §8, critical): the sidebar is `fixed` — out of flow —
 * and `main` carries an EXPLICIT desktop offset (`mainOffsetClass`) that tracks
 * the collapsed rail. The offset must not depend on the sidebar happening to
 * reserve space, or content renders under it. `components/app-frame.test.tsx`
 * asserts the offset so the regression cannot return.
 *
 * The twelve-x FX Hub suite renders inside this shell like every other
 * destination (#1664 retired its standalone chrome). It stays DB-exempt in
 * lib/nav.ts because it reads its own research feed (isTwelveXConfigured)
 * rather than the main dashboard backend.
 */
export default function AppFrame({ children }: { children: ReactNode }) {
  const pathname = usePathname();
  const { dbStatus } = useDashboard();
  const { sidebarCollapsed } = useAppShell();

  // DB-down gate: when the backend is unconfigured/unreachable and the route is
  // not allowlisted, swap the page for the standardized card. The shell itself
  // (Sidebar, MobileAppBar, CommandPalette) stays mounted in every case, so the
  // app still opens and the owner can navigate to Pipeline/Settings.
  const gated = dbStatus !== 'ok' && !isDbExempt(pathname);

  return (
    <div className="min-h-screen">
      <Suspense
        fallback={
          // Out of flow, like the real rail — `main` owns the offset, so the
          // fallback must not reserve flex space either (it would double it).
          <aside className="fixed top-0 left-0 hidden h-screen w-[260px] shrink-0 border-r border-hair bg-surface md:block" />
        }
      >
        <Sidebar />
      </Suspense>
      <main
        className={`flex min-h-0 min-w-0 flex-1 flex-col max-h-screen overflow-y-auto transition-[padding] duration-300 ease-out ${mainOffsetClass(
          sidebarCollapsed
        )}`}
      >
        <MobileAppBar />
        <CommandPalette />
        <div className="flex min-h-0 flex-1 flex-col">
          {gated ? <DbUnavailable status={dbStatus} /> : <FxHubOnlyGuard>{children}</FxHubOnlyGuard>}
        </div>
      </main>
      {/* Desk+ research/portfolio digichat popup (#3422); no-ops when env off. */}
      <DigichatPopup />
    </div>
  );
}
