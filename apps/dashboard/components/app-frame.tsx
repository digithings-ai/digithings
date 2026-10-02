'use client';

import { ReactNode, Suspense } from 'react';
import { usePathname } from 'next/navigation';
import Sidebar from '@/components/sidebar';
import MobileAppBar from '@/components/mobile-app-bar';
import CommandPalette from '@/components/command-palette';
import DigichatPopup from '@/components/digichat-popup';
import DeskShell from '@/components/desk/shell/DeskShell';
import FxHubOnlyGuard from '@/components/fx-hub-only-guard';
import DbUnavailable from '@/components/db-unavailable';
import { useDashboard } from '@/lib/dashboard-context';
import { isDeskShellEnabled } from '@/lib/desk/flag';
import { isDbExempt } from '@/lib/nav';

/**
 * App frame: the dashboard shell (sidebar + page chrome) for all routes.
 *
 * The twelve-x FX Hub suite renders inside this shell like every other
 * destination (#1664 retired its standalone chrome). It stays DB-exempt in
 * lib/nav.ts because it reads its own research feed (isTwelveXConfigured)
 * rather than the main dashboard backend.
 */
export default function AppFrame({ children }: { children: ReactNode }) {
  const pathname = usePathname();
  const { dbStatus } = useDashboard();

  // DB-down gate: when the backend is unconfigured/unreachable and the route is
  // not allowlisted, swap the page for the standardized card. The shell itself
  // (Sidebar, MobileAppBar, CommandPalette) stays mounted in every case, so the
  // app still opens and the owner can navigate to System/Settings.
  const gated = dbStatus !== 'ok' && !isDbExempt(pathname);
  const body = gated ? <DbUnavailable /> : <FxHubOnlyGuard>{children}</FxHubOnlyGuard>;

  // Default off. A shell-only deploy keeps the current brief instead of an
  // empty terminal. NEXT_PUBLIC_DESK_SHELL is build-time (static export).
  if (isDeskShellEnabled()) {
    return (
      <Suspense
        fallback={
          <div data-desk-shell="" data-document-scroll="locked" className="h-dvh overflow-hidden" />
        }
      >
        <DeskShell>{body}</DeskShell>
        <CommandPalette />
      </Suspense>
    );
  }

  return (
    <div className="flex min-h-screen">
      <Suspense fallback={<aside className="w-[260px] shrink-0 border-r border-hair bg-surface" />}>
        <Sidebar />
      </Suspense>
      <main className="flex min-h-0 min-w-0 flex-1 flex-col overflow-y-auto max-h-screen">
        <MobileAppBar />
        <CommandPalette />
        <div className="flex min-h-0 flex-1 flex-col">{body}</div>
      </main>
      {/* Desk+ research/portfolio digichat popup (#3422); no-ops when env off. */}
      <DigichatPopup />
    </div>
  );
}
